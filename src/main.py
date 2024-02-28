import os
import json
import logging
import copy
from datetime import datetime

try:
    import src.utils as utils
    import src.dialogue_manager as dialogue_manager
    import src.answer_parser as answer_parser
except ImportError:
    try:
        import utils
        import dialogue_manager
        import answer_parser
    except ImportError as e:
        print('ERROR:')
        print(e)
        exit(-1)






def mainloop(manager, config):
    stop = False
    while not stop:
        out = manager.call(config)
        logging.info('dm:\n%s', out)
        if config.get('stuck', 0):
            return manager
        manager, stop = interpret_dm(manager, out, config)
    return manager



def fill_chunk(cf_manager, config):
    cf_manager.dialogue = []
    stop = False
    while not stop:
        out = cf_manager.call(config)
        if config.get('stuck', 0):
            return cf_manager 
        cf_manager, stop = interpret_cf(cf_manager, out, config)
    return cf_manager


def run_dialogue(a_parser, config):
    stop = False
    while not stop:
        out = a_parser.call(config)
        if config.get('stuck', 0):
            return a_parser
        a_parser, stop = interpret_parser(a_parser, out, config)
    return a_parser

def interpret_parser(parser, out, config):
    """interprets the output of the AnswerParsing module and runs the appropriate functions

    Args:
        parser (AnswerParsing): AnswerParsing object
        output (str): output given by the CFM as serialized json
        config (dict): config info

    Returns:
        parser: AnswerParsing object
        stop: boolean signaling to stop the loop (true of next action is 'return')
    """
    json_out = json.loads(out)
    json_out['next action'] = json_out["next action"].lower()


    if json_out['next action'] == 'repeat_question':
        logging.info('answer_parsing --> repeat_question')
        new_q = parser.repeat_question(config)
        json_q = json.loads(new_q)
        # print('GENERATED QUESTION:')
        print(json_q['new question'])
        if not config['autouser']:
            a = input('ANSWER: ')
        else:
            a = utils.auto_user(json_q['new question'], config)
            print('ANSWER:')
            print(a)
        interaction = {
            'module': 'user',
            'prompt': json_q['new question'],
            'output': a
        }
        utils.add_to_transcript(interaction, config)
        # TBD: check if the answer is valid (e.g. not empty)
        parser.dialogue.append({'Assistant': f'{json_q["new question"]}'})
        parser.dialogue.append({'User': a})
        logging.info('repeat_question --> answer_parsing:\n%s', json.dumps(parser.dialogue))
        return parser, False
    
    elif json_out['next action'] == 'follow_up_question':
        logging.info('answer_parsing --> follow_up_question')
        q = parser.follow_up_question(config)
        json_q = json.loads(q)
        # print('GENERATED QUESTION:')
        print(json_q['question'])
        if not config['autouser']:
            a = input('ANSWER: ')
        else:
            a = utils.auto_user(json_q['question'], config)
            print('ANSWER:')
            print(a)
        interaction = {
            'module': 'user',
            'prompt': json_q['question'],
            'output': a
        }
        utils.add_to_transcript(interaction, config)
        # TBD: check if the answer is valid (e.g. not empty)
        parser.dialogue.append({'Assistant': f'{json_q["question"]}'})
        parser.dialogue.append({'User': a})
        logging.info('follow_up_question --> answer_parsing:\n%s', json.dumps(parser.dialogue))
        return parser, False
    
    elif json_out['next action'] == 'information_extraction':
        logging.info('answer_parsing --> information_extraction')
        info = parser.information_extraction(config)
        logging.info("information_extraction --> form_filling:\n%s", info)
        filled = parser.form_filling(config)
        logging.info("form_filling --> cfm:\n%s", filled)
        return parser, True
    
    else:
        return parser, False



def interpret_cf(cfm, out, config):
    """interprets the output of the Chunk Filling manager module and runs the appropriate functions

    Args:
        cfm (ChunkFiller): Chunk Filling Dialogue Manger object
        output (str): output given by the CFM as serialized json
        config (dict): config info

    Returns:
        cfm: CFM object
        stop: boolean signaling to stop the loop (true of next action is 'return')
    """
    json_out = json.loads(out)
    json_out['next action'] = json_out["next action"].lower()

    if json_out['next action'] == 'question_generation':
        logging.info('cfm --> question_generation')
        q = cfm.question_generation(config)
        json_q = json.loads(q)
        flds = json_q['fields']
        if not flds:
            no_flds = True
        elif flds[0] == "":
            no_flds = True
        else:
            no_flds = False
        if json_q['question'] is None or no_flds:
            logging.warning('no new question could be generated, returning to CFM')
            logging.info('question_generation --> cfm')
            tmp = [json_out['next action']]
            if len(cfm.state['last action']) > 5:
                tmp.extend(cfm.state['last action'][:-1])
            else:
                tmp.extend(cfm.state['last action'])
            cfm.state['last action'] = tmp
            cfm.state['last question'] = "question_generation did not find a new question to ask and suggests that fill_validation be called"
            return cfm, False
        cfm.state['last question'] = json_q['question']
        # print('GENERATED QUESTION:')
        print(json_q['question'])
        if not config['autouser']:
            a = input('ANSWER: ')
        else:
            a = utils.auto_user(json_q['question'], config)
            print('ANSWER:')
            print(a)
        interaction = {
            'module': 'user',
            'prompt': json_q['question'],
            'output': a
        }
        utils.add_to_transcript(interaction, config)
        # TBD: check if the answer is valid (e.g. not empty)

        logging.info('question_generation --> answer_parsing:\n%s', q)

        chunk_copy = copy.deepcopy(cfm.chunk)
        info_copy = copy.deepcopy(cfm.info)
        open_chunk = utils.get_unanswered(chunk_copy, cfm.state['fields'])
        parser = answer_parser.AnswerParser(
            [
                {"Assistant": json_q['question']},
                {"User": a}
            ],
            json_q['fields'],
            open_chunk,
            info_copy
        )
        # call its main loop
        # get object returned as well as the filled out part and dialogue
        parser = run_dialogue(parser, config)

        # put filled out chunk from parser into chunk from cfm
        cfm.chunk = utils.fill_in_parts(cfm.chunk, parser.chunk)

        # append dialogue from parser to dialogue of cfm (extend)
        cfm.dialogue.extend(parser.dialogue)
        for key, value in parser.info.items():
            cfm.info[key] = value

        cfm.state = utils.update_cf_state(cfm.state, cfm.chunk)
        tmp = [json_out['next action']]
        if len(cfm.state['last action']) > 5:
            tmp.extend(cfm.state['last action'][:-1])
        else:
            tmp.extend(cfm.state['last action'])
        cfm.state['last action'] = tmp
        return cfm, False


    elif json_out['next action'] == 'fill_validation':
        logging.info('cfm --> fill_valdiation')
        chunk = cfm.fill_validation(config)
        logging.info('fill_valdiation --> cfm:\n%s', chunk)
        tmp = [json_out['next action']]
        if len(cfm.state['last action']) > 5:
            tmp.extend(cfm.state['last action'][:-1])
        else:
            tmp.extend(cfm.state['last action'])
        cfm.state['last action'] = tmp
        return cfm, False


    elif json_out['next action'] == 'stop':
        logging.info('cfm --> stop')
        tmp = [json_out['next action']]
        if len(cfm.state['last action']) > 5:
            tmp.extend(cfm.state['last action'][:-1])
        else:
            tmp.extend(cfm.state['last action'])
        cfm.state['last action'] = tmp
        logging.info("stop --> dm")
        return cfm, True
    
    else:
        return cfm, False

    
def interpret_dm(manager, output, config):
    """interprets the output of the Dialogue manager module and runs the appropriate functions

    Args:
        manager (DialogueManager): Dialogue Manger object
        output (str): output given by the DM as serialized json
        config (dict): config info

    Returns:
        manager: DM object
        stop: boolean signaling to stop the loop (true of next action is 'stop')
    """
    if isinstance(output, str):
        json_out = json.loads(output)
    else:
        json_out = output

    json_out['next action'] = json_out["next action"].lower()
    

    if json_out['next action'] == 'form_chunks':
        logging.info('dm --> form_chunks')
        manager.form_chunks(config)
        tmp = [json_out['next action']]
        if len(manager.state['last action']) > 5:
            tmp.extend(manager.state['last action'][:-1])
        else:
            tmp.extend(manager.state['last action'])
        manager.state['last action'] = tmp
        return manager, False

    elif json_out['next action'] == 'fill_chunk':
        ctwo = json_out['chunk to work on']
        cf_manager = manager.cf_managers.get(ctwo, -1)
        if cf_manager == -1:
            if not manager.chunks:    
                manager, _ = interpret_dm(manager, json.dumps({"next action": "form_chunks", "chunk to work on": ""}), config)
                return manager, False
            else:
                manager, _ = interpret_dm(manager, json.dumps({"next action": "stop", "chunk to work on": ""}), config)
                return manager, True
        manager.cf_managers[ctwo] = fill_chunk(cf_manager, config)
        chunk = manager.cf_managers[ctwo].chunk
        for key, value in chunk.items():
            manager.form[key] = value
        manager.dialogue.extend(manager.cf_managers[ctwo].dialogue)
        tmp = [json_out['next action']]
        if len(manager.state['last action']) > 5:
            tmp.extend(manager.state['last action'][:-1])
        else:
            tmp.extend(manager.state['last action'])
        manager.state['last action'] = tmp
        manager = utils.update_dm_state(manager)
        return manager, False

    elif json_out['next action'] == 'stop':
        tmp = [json_out['next action']]
        if len(manager.state['last action']) > 5:
            tmp.extend(manager.state['last action'][:-1])
        else:
            tmp.extend(manager.state['last action'])  
        manager.state['last action'] = tmp
        return manager, True
    
    else:
        return manager, False
    
    

def main(config):
    form = utils.load_form(config['form'])
    manager = dialogue_manager.Dialogue_Manager(form)
    out_dir = utils.get_out_dir()
    config['out_dir'] = out_dir
    now = datetime.now()
    date_n_time = now.strftime("%m/%d/%Y, %H:%M:%S")
    config['date and time'] = date_n_time

    manager = mainloop(manager, config)
    with open(os.path.join(config['out_dir'], 'filled-form.json'), 'w') as f:
        json.dump(manager.form, f)
    with open(os.path.join(config['out_dir'], 'dm-state.json'), 'w') as f:
        json.dump(manager.state, f)
    cfm_states = {}
    ext_info = {}
    for cfm in manager.cf_managers:
        cfm_states[cfm] = manager.cf_managers[cfm].state
        for key, val in manager.cf_managers[cfm].info.items():
            ext_info[key] = val
    with open(os.path.join(config['out_dir'], 'info.json'), 'w') as f:
        json.dump(ext_info, f)
    with open(os.path.join(config['out_dir'], 'cfm-states.json'), 'w') as f:
        json.dump(cfm_states, f)
    with open(os.path.join(config['out_dir'], 'config.json'), 'w') as f:
        json.dump(config, f)
    with open(os.path.join(config['out_dir'], 'dialogue.json'), 'w') as f:
        json.dump(manager.dialogue, f)


if __name__ == '__main__':
    logging.basicConfig(filename='logs/run.log', 
                        level=logging.INFO, 
                        filemode='w', 
                        format='%(levelname)s: %(message)s')
    config = utils.load_config("config/config.json") 
    config = utils.check_specials(config)
    for i in range(config['num_dialogues']):
        main(config)
        
    
