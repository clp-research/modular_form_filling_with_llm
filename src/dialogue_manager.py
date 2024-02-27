import json
import os
import logging

try:
    import src.utils as utils
    import src.chunk_filling as chunk_filling
    import src.output_matching as output_matching
except ImportError:
    try:
        import output_matching
        import utils
        import chunk_filling
    except ImportError as e:
        print('ERROR:')
        print(e)
        exit(-1)



class Dialogue_Manager:
    def __init__(self, form, arg = None):
        self.state = utils.init_dl_state()
        self.grouping = {}
        self.chunks = {}
        self.cf_managers = {}
        self.form = form
        self.prompts = self.load_prompts()
        self.dialogue = []

    def call(self, config, fb = False):
        interaction = {'module': 'Dialogue Manager'}
        if all([self.state['chunks'][f] == 'validated' for f in self.state['chunks']]) and self.chunks:
            interaction['output'] = json.dumps({"next action": "stop", "chunk to work on": None})
            interaction['prompt'] = f'used fallback mechanism on current state: {json.dumps(self.state)}'
            utils.add_to_transcript(interaction, config)
            return json.dumps({"next action": "stop"})
        if config['model']['dialogue_manager'] == 'dummy' or fb:
            action = None
            if not self.state['last action']:
                action = 'form_chunks'
            elif self.state['chunks']:
                vals = []
                for name in self.state['chunks']:
                    if self.state['chunks'][name] == "validated":
                        vals.append(True)
                    else:
                        vals.append(False)
                if all(vals):
                    action = 'stop'
            if not action:
                action = 'fill_chunk'
            self.state['last action'] = action
            ctwo = None
            if action == 'fill_chunk':
                for chunk, cond in self.state['chunks'].items():
                    if cond in ['empty', 'partially filled']:
                        ctwo = chunk
                        break
                if not ctwo:
                    logging.warning('Could not find a chunk to work on for `fill_chunk`, defaulting to first chunk')
                    ctwo = list(self.state['chunks'].keys())[0]
            ret = {
                "next action": action,
                "chunk to work on": ctwo
            }
            interaction['output'] = json.dumps(ret)
            interaction['prompt'] = f'used fallback mechanism on current state: {json.dumps(self.state)}'
            utils.add_to_transcript(interaction, config)
            return json.dumps(ret)
        else:
            prompt = self.prompts['dialogue_manager']
            state_str = json.dumps(self.state)
            prompt = prompt.replace('[State]', state_str)
            messages = [
                {'role': 'system', 'content': ''},
                {'role': 'user', 'content': prompt}
            ]
            out = utils.make_api_call(messages, config['model']['dialogue_manager'], config)
            span, out_trim = output_matching.match_output(out, 'dman')
            if span is None:
                logging.warning('Output of DM model did not match expected pattern:\n%s', out)
                messages[1]['content'] += ('\n\n The output needs to fit the following Regular Expression:\n ' 
                                            + output_matching.re_dialogue_manager.pattern)
                config['temperature'] = config['high temp']
                out = utils.make_api_call(messages, config['model']['dialogue_manager'], config)
                config['temperature'] = config['base temp']
                span, out_trim = output_matching.match_output(out, 'dman')
                if span is None:
                    logging.warning('Output of DM model did not match expected pattern AGAIN:\n%s\ngoing with fallback mechanism', out)
                    return self.call(config, fb=True)  
            interaction['prompt'] = messages[1]['content']
            interaction['output'] = out_trim
            utils.add_to_transcript(interaction, config)
            return out_trim


    def form_chunks(self, config):
        logging.info('form_chunks --> question_extraction')
        extr_questions = self.question_extraction(config)
        self.q_summaries = json.loads(extr_questions)
        ks = list(self.q_summaries.keys())
        splits = []
        for i in range(0, len(ks), config['grouping_size']):
            splits.append(ks[i:i+config['grouping_size']])
        
        groups = {}

        for split in splits:
            split_qs = {}
            for key in split:
                split_qs[key] = self.q_summaries[key]
            logging.info('question_extraction --> question_grouping:\n%s', json.dumps(split_qs))
            split_groups = self.question_grouping(json.dumps(split_qs), config)
            logging.info('question_grouping --> grouping_validation:\n%s', split_groups)
            split_groups_val = self.grouping_validation(split_groups, json.dumps(split_qs), config)
            split_groups_l = json.loads(split_groups_val)
            gk = list(groups.keys())

            for key, value in split_groups_l.items():
                if key in gk:
                    groups[f'{key} 1'] = groups[key]
                    del groups[key]
                    groups[f'{key} 2'] = value
                elif f'{key} 2' in gk:
                    i = 2
                    while f'{key} {i}' in gk:
                        i += 1
                    groups[f'{key} {i}'] = value
                else:
                    groups[key] = value

        logging.info('grouping_validation --> form_chunks:\n%s', json.dumps(groups))
        self.grouping = groups
        self.init_cf_managers()
        logging.info('form_chunks --> dm')
        return json.dumps(groups)
    

    def question_grouping(self, questions, config, fb = False):
        interaction = {"module": "Question Grouping"}
        if config['model']['question_grouping'] == "dummy" or fb:
            if isinstance(questions, str):
                questions = json.loads(questions)
            size = 4
            ks = list(questions.keys())
            groups = {}
            for i in range(0, len(ks), size):
                groups['Group '+str((i//size)+1)] = ks[i:i+size]
            interaction['prompt'] = f'used fallback mechanism on extracted questions: {json.dumps(questions)}'
            interaction['output'] = json.dumps(groups)
            utils.add_to_transcript(interaction, config)
            return json.dumps(groups)
        else:
            if isinstance(questions, dict):
                questions = json.dumps(questions)
            prompt = self.prompts['question_grouping']
            prompt = prompt.replace('[Insert]', questions)
            messages = [
                {'role': 'system', 'content': ''},
                {'role': 'user', 'content': prompt}
            ]
            out = utils.make_api_call(messages, config['model']['question_grouping'], config)
            span, out_trim = output_matching.match_output(out, 'qgrp')
            checked = utils.check_grouping(out_trim, self.form, questions)
            if checked is None:
                span = None
            else:
                out_trim = checked
            if span is None:
                logging.warning('Output of question_grouping model did not match expected pattern:\n%s', out)
                messages[1]['content'] += ('\n\n The output needs to fit the following Regular Expression:\n ' 
                                            + output_matching.re_question_grouping.pattern)
                config['temperature'] = config['high temp']
                out = utils.make_api_call(messages, config['model']['question_grouping'], config)
                config['temperature'] = config['base temp']
                span, out_trim = output_matching.match_output(out, 'qgrp')
                checked = utils.check_grouping(out_trim, self.form, questions)
                if checked is None:
                    span = None
                else:
                    out_trim = checked
                if span is None:
                    logging.warning('Output of question_grouping model did not match expected pattern AGAIN:\n%s\ngoing with fallback mechanism', out)
                    return self.question_grouping(questions, config, fb=True)  
            groups = json.loads(out_trim)
            val_groups = {}
            qs = json.loads(questions)
            for key, item in groups.items():
                val_groups[key] = []
                for lbl, q in qs.items():
                    if q in item or lbl in item:
                        val_groups[key].append(lbl)
            interaction['prompt'] = messages[1]['content']
            interaction['output'] = json.dumps(val_groups)
            utils.add_to_transcript(interaction, config)
            return json.dumps(val_groups)


    def question_extraction(self, config, fb = False):
        interaction = {'module': 'Question Extractor'}
        qs = {}
        if config['model']['question_extraction'] == "dummy" or fb:
            inp = {}
            for lbl in self.form:
                inp[lbl] = []
                summary = ''
                for q in self.form[lbl]:
                    summary += q + ', '
                    inp[lbl].append(q)
                summary = summary[:-2]
                qs[lbl] = summary
            interaction['prompt'] = f'used fallback mechanism on form labels: {json.dumps(inp)}'
            interaction['output'] = json.dumps(qs)
            utils.add_to_transcript(interaction, config)
            return json.dumps(qs)
        else:
            for k in self.form:
                prompt = self.prompts['question_extraction']
                prompt = prompt.replace('[Insert]', json.dumps({k: self.form[k]}))
                messages = [
                    {'role': 'system', 'content': ''},
                    {'role': 'user', 'content': prompt}
                ]
                out = utils.make_api_call(messages, config['model']['question_extraction'], config)
                span, out_trim = output_matching.match_output(out, 'qext')
                if span is None:
                    logging.warning('Output of question_extraction model did not match expected pattern:\n%s', out)
                    messages.extend([
                        {'role': 'assistant', 'content': out_trim},
                        {'role': 'user', 'content': "The output needs to be in the format of the RETURN FORM."}
                    ])
                    config['temperature'] = config['high temp']
                    out = utils.make_api_call(messages, config['model']['question_extraction'], config)
                    config['temperature'] = config['base temp']
                    span, out_trim = output_matching.match_output(out, 'qext')
                    if span is None:
                        logging.warning('Output of question_extraction model did not match expected pattern AGAIN:\n%s\ngoing with fallback mechanism', out)
                        summary = ''
                        for q in self.form[k]:
                            summary += q + ', '
                        summary = summary[:-2]
                        qs[k] = summary
                        messages[1]['content'] = 'Going with fallback mechanism and use form field titles'
                        interaction['output'] = json.dumps({"question": qs[k]})
                        interaction['input'] = messages[1]['content']
                        utils.add_to_transcript(interaction, config)
                        continue
                interaction['input'] = messages[1]['content']
                interaction['output'] = out_trim
                utils.add_to_transcript(interaction, config)
                out_dict = json.loads(out_trim) 
                qs[k] = out_dict['summary']
            return json.dumps(qs)


    def grouping_validation(self, groups, questions, config, fb = False):
        interaction = {'module': 'Grouping validator'}
        if config['model']['grouping_validation'] == "dummy" or fb:
            if isinstance(groups, dict):
                groups = json.dumps(groups)
            if isinstance(questions, dict):
                questions = json.dumps(questions)
            interaction['input'] = f"using fallback mechanism on groups: {groups}\n\nand extarcted questions: {questions}"
            interaction['output'] = groups
            utils.add_to_transcript(interaction, config)
            return groups
        else:
            if isinstance(questions, dict):
                questions = json.dumps(questions)
            if isinstance(groups, dict):
                groups = json.dumps(groups)
            prompt = self.prompts['grouping_validation']
            prompt = prompt.replace('[Insert 1]', questions)
            prompt = prompt.replace('[Insert 2]', groups)
            # print(prompt)
            messages = [
                {'role': 'system', 'content': ''},
                {'role': 'user', 'content': prompt}
            ]
            out = utils.make_api_call(messages, config['model']['grouping_validation'], config)
            span, out_trim = output_matching.match_output(out, 'qgrp')
            if span is None:
                logging.warning('Output of grouping_validation model did not match expected pattern:\n%s', out)
                messages[1]['content'] += ('\n\n The output needs to fit the following Regular Expression:\n ' 
                                            + output_matching.re_question_grouping.pattern)
                config['temperature'] = config['high temp']
                out = utils.make_api_call(messages, config['model']['grouping_validation'], config)
                config['temperature'] = config['base temp']
                span, out_trim = output_matching.match_output(out, 'qgrp')
                if span is None:
                    logging.warning('Output of grouping_validation model did not match expected pattern AGAIN:\n%s\ngoing with fallback mechanism', out)
                    return self.grouping_validation(groups, questions, config, fb=True)  
            interaction['input'] = messages[1]['content']
            interaction['output'] = out_trim
            utils.add_to_transcript(interaction, config)
            return out_trim
        

    def init_cf_managers(self):
        if not self.grouping:
            logging.error('managers cannot be initiallized before grouping fields into chunks. TBD: recover')
            exit(-1)
        for key, val in self.grouping.items():
            self.chunks[key] = {field_name: self.form[field_name] for field_name in val}
            self.state['chunks'][key] = 'empty'
            self.cf_managers[key] = chunk_filling.ChunkFiller(self.form, 
                                                               self.chunks[key], 
                                                               key)
            

    def load_prompts(self):
        prompts = {}
        with open('prompt_blueprints.json', 'r') as f:
            bp_file_paths = json.load(f)
        for module in ['question_grouping', 'question_extraction', 'grouping_validation', 'dialogue_manager']:
            with open(os.path.join('blueprints', bp_file_paths[module]), 'r') as f:
                prompts[module] = f.read()
        return prompts
            
