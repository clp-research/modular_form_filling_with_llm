import logging
import os
import json 

try:
    import src.utils as utils
    import src.output_matching as output_matching
except ImportError:
    try:
        import output_matching
        import utils
    except ImportError as e:
        print('ERROR:')
        print(e)
        exit(-1)


class AnswerParser:
    def __init__(self, dialogue, fields, chunk, info):
        self.prompts = self.load_prompts()
        self.dialogue = dialogue
        self.fields = fields
        self.chunk = chunk
        self.info = info


    def call(self, config, fb=False):
        interaction = {'module': 'Answer Parser'}
        if config['model']['answer_parsing'] == "dummy" or fb:
            ret = {
                "next action": "information_extraction"
            }
            interaction['output'] = json.dumps(ret)
            interaction['prompt'] = f'used fallback mechanism on dialogue: {json.dumps(self.dialogue)}'
            utils.add_to_transcript(interaction, config)
            return json.dumps(ret)
        else:
            prompt = self.prompts['answer_parsing']
            prompt = prompt.replace('[Insert 1]', json.dumps(self.dialogue))
            prompt = prompt.replace('[Insert 2]', json.dumps(self.chunk))
            prompt = prompt.replace('[Insert 3]', json.dumps(self.fields))
            messages = [
                {'role': 'system', 'content': ''},
                {'role': 'user', 'content': prompt}
            ]
            out = utils.make_api_call(messages, config['model']['answer_parsing'], config)
            span, out_trim = output_matching.match_output(out, 'apar')
            if span is None:
                logging.warning('Output of answer_parsing model did not match expected pattern:\n%s', out)
                messages.extend([
                    {'role': 'assistant', 'content': out},
                    {'role': 'user', 'content': ('\n\n The output needs to fit the following Regular Expression:\n ' 
                                            + output_matching.re_answer_parsing.pattern)}
                ])
                config['temperature'] = config['high temp']
                out = utils.make_api_call(messages, config['model']['answer_parsing'], config)
                config['temperature'] = config['base temp']
                span, out_trim = output_matching.match_output(out, 'apar')
                if span is None:
                    logging.warning('Output of answer_parsing model did not match expected pattern AGAIN:\n%s\ngoing with fallback mechanism', out)
                    return self.call(config, fb = True)  
            interaction['output'] = out_trim
            interaction['prompt'] = messages[1]['content']
            utils.add_to_transcript(interaction, config)
            return out_trim
        

    def repeat_question(self, config, fb=False):
        interaction = {'module': 'Repeated Question Generator'}
        if config['model']['repeat_question'] == "dummy" or fb:
            last_q = self.dialogue[-2]['Assistant']
            ret = {
                "question": f"Your answer did not match what was expected as an answer. \n{last_q}"
            }
            interaction['output'] = json.dumps(ret)
            interaction['prompt'] = f'used fallback mechanism on last question: {last_q}'
            utils.add_to_transcript(interaction, config)
            return json.dumps(ret)
        else:
            prompt = self.prompts['repeat_question']
            prompt = prompt.replace('[Insert 1]', json.dumps(self.dialogue))
            prompt = prompt.replace('[Insert 3]', json.dumps(self.chunk))
            prompt = prompt.replace('[Insert 2]', json.dumps(self.fields))
            messages = [
                {'role': 'system', 'content': ''},
                {'role': 'user', 'content': prompt}
            ]
            out = utils.make_api_call(messages, config['model']['repeat_question'], config)
            span, out_trim = output_matching.match_output(out, 'repq')
            if span is None:
                logging.warning('Output of repeat_question model did not match expected pattern:\n%s', out)
                messages[1]['content'] += ('\n\n The output needs to fit the following Regular Expression:\n ' 
                                            + output_matching.re_repeat_question.pattern)
                config['temperature'] = config['high temp']
                out = utils.make_api_call(messages, config['model']['repeat_question'], config)
                config['temperature'] = config['base temp']
                span, out_trim = output_matching.match_output(out, 'repq')
                if span is None:
                    logging.warning('Output of repeat_question model did not match expected pattern AGAIN:\n%s\ngoing with fallback mechanism', out)
                    return self.repeat_question(config, fb = True)  
            interaction['output'] = out_trim
            interaction['prompt'] = messages[1]['content']
            utils.add_to_transcript(interaction, config)
            return out_trim


    def follow_up_question(self, config, fb=False):
        interaction = {'module': 'Follow-up Question Generator'}
        if config['model']['follow_up_question'] == "dummy" or fb:
            last_q = self.dialogue[-2]['Assistant']
            ret = {
                "question": last_q
            }
            interaction['output'] = json.dumps(ret)
            interaction['prompt'] = f'used fallback mechanism on last question: {last_q}'
            utils.add_to_transcript(interaction, config)
            return json.dumps(ret)
        else:
            prompt = self.prompts['follow_up_question']
            prompt = prompt.replace('[Insert 1]', json.dumps(self.dialogue))
            prompt = prompt.replace('[Insert 2]', json.dumps(self.fields))
            prompt = prompt.replace('[Insert 3]', json.dumps(self.chunk))
            messages = [
                {'role': 'system', 'content': ''},
                {'role': 'user', 'content': prompt}
            ]
            out = utils.make_api_call(messages, config['model']['follow_up_question'], config)
            span, out_trim = output_matching.match_output(out, 'fupq')
            if span is None:
                logging.warning('Output of follow_up_question model did not match expected pattern:\n%s', out)
                messages[1]['content'] += ('\n\n The output needs to fit the following Regular Expression:\n ' 
                                            + output_matching.re_follow_up_question.pattern)
                config['temperature'] = config['high temp']
                out = utils.make_api_call(messages, config['model']['follow_up_question'], config)
                config['temperature'] = config['base temp']
                span, out_trim = output_matching.match_output(out, 'fupq')
                if span is None:
                    logging.warning('Output of follow_up_question model did not match expected pattern AGAIN:\n%s\ngoing with fallback mechanism', out)
                    return self.follow_up_question(config, fb = True)  
            interaction['output'] = out_trim
            interaction['prompt'] = messages[1]['content']
            utils.add_to_transcript(interaction, config)
            return out_trim
        

    def information_extraction(self, config, fb=False):
        interaction = {'module': 'information_extraction'}
        if config['model']['information_extraction'] == "dummy" or fb:
            ret = {}
            qs = self.dialogue[::2]
            ans = self.dialogue[1::2]
            for i in range(len(qs)):
                question = qs[i]['Assistant'].split('\nYour Options are :')[0]
                ret[question] = ans[i]['User']
            for key in ret:
                self.info[key] = ret[key]
            interaction['output'] = json.dumps(ret)
            interaction['prompt'] = f'used fallback mechanism on dialogue: {json.dumps(self.dialogue)}'
            utils.add_to_transcript(interaction, config)
            return json.dumps(ret)
        else:
            prompt = self.prompts['information_extraction']
            prompt = prompt.replace('[Insert 2]', json.dumps(self.dialogue))
            messages = [
                {'role': 'system', 'content': ''},
                {'role': 'user', 'content': prompt}
            ]
            out = utils.make_api_call(messages, config['model']['information_extraction'], config)
            span, out_trim = output_matching.match_output(out, 'iext')
            if span is None:
                logging.warning('Output of information_extraction model did not match expected pattern:\n%s', out)
                messages.extend([
                    {'role': 'assistant', 'content': out},
                    {'role': 'user', 'content': ('\n\n The output needs to fit the following Regular Expression:\n ' 
                                            + output_matching.re_information_extraction.pattern)}
                ])
                config['temperature'] = config['high temp']
                out = utils.make_api_call(messages, config['model']['information_extraction'], config)
                config['temperature'] = config['base temp']
                span, out_trim = output_matching.match_output(out, 'iext')
                if span is None:
                    logging.warning('Output of information_extraction model did not match expected pattern AGAIN:\n%s\ngoing with fallback mechanism', out)
                    return self.information_extraction(config, fb = True)  
            new_info = json.loads(out_trim)
            for key in new_info:
                self.info[key] = new_info[key]
            interaction['output'] = out_trim
            interaction['prompt'] = messages[1]['content']
            utils.add_to_transcript(interaction, config)
            return out_trim
        

    def form_filling(self, config, fb = False):
        interaction = {'module': 'Form Filler'}
        if config['model']['form_filling'] == "dummy" or fb:
            self.chunk = utils.find_and_fill(self.chunk, self.info)
            interaction['output'] = json.dumps(self.chunk)
            interaction['prompt'] = f'used fallback mechanism on extracted information: {json.dumps(self.info)} \n\nand chunk of form: {json.dumps(self.chunk)}'
            utils.add_to_transcript(interaction, config)
            return json.dumps(self.chunk)
        else:
            prompt = self.prompts['form_filling']
            prompt = prompt.replace('[Insert 1]', json.dumps(self.chunk))	
            prompt = prompt.replace('[Insert 2]', json.dumps(self.info))	
            prompt = prompt.replace('[Insert 3]', json.dumps(self.fields))	
            messages = [
                {'role': 'system', 'content': ''},
                {'role': 'user', 'content': prompt}
            ]
            out = utils.make_api_call(messages, config['model']['form_filling'], config)
            span, out_trim = output_matching.match_output(out, 'ffil')
            fail = False
            if span is None:
                fail = True
            elif not utils.check_likeness(self.chunk, json.loads(out_trim)):
                fail = True
            if fail:
                logging.warning('Output of form_filling model did not match expected pattern:\n%s', out)
                messages.extend([
                    {"role": "assistant", "content": out_trim},
                    {"role": "user", "content": "Be sure to return the entire FORM given to you with only the appropriate answer fields filled out."}
                ])
                config['temperature'] = config['high temp']
                out = utils.make_api_call(messages, config['model']['form_filling'], config)
                config['temperature'] = config['base temp']
                span, out_trim = output_matching.match_output(out, 'ffil')
                fail = False
                if span is None:
                    fail = True
                elif not utils.check_likeness(self.chunk, json.loads(out_trim)):
                    fail = True
                if fail:
                    logging.warning('Output of form_filling model did not match expected pattern AGAIN:\n%s\ngoing with fallback mechanism', out)
                    return self.form_filling(config, fb = True)
            new = json.loads(out_trim)
            for key in new:
                self.chunk[key] = new[key]
            interaction['output'] = out_trim
            interaction['prompt'] = messages[1]['content']
            utils.add_to_transcript(interaction, config)
            return out_trim
        

    def load_prompts(self):
        prompts = {}
        with open('prompt_blueprints.json', 'r') as f:
            bp_file_paths = json.load(f)
        for module in ['answer_parsing', 'information_extraction', 'follow_up_question', 'repeat_question', 'form_filling']:
            with open(os.path.join('blueprints', bp_file_paths[module]), 'r') as f:
                prompts[module] = f.read()
        return prompts