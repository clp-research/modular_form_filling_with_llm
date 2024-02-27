import os
import json
import logging
import copy

try:
    import src.utils as utils
    import src.output_matching as output_matching
except ImportError:
    try:
        import utils
        import output_matching
    except ImportError as e:
        print('ERROR:')
        print(e)
        exit(-1)

class ChunkFiller:
    def __init__(self, form, chunk, name):
        self.state = utils.init_cf_state(chunk)
        self.chunk = chunk
        self.form = form
        self.name = name
        self.info = {}
        self.dialogue = []
        self.last_question = {
            'q': None,
            'a': None
        }
        self.prompts = self.load_prompts()


    def call(self, config, fb = False):
        interaction = {'module': 'Chunk Filler'}
        if all([self.state['fields'][f] == 'validated' for f in self.state['fields']]):
            interaction['output'] = json.dumps({"next action": "stop"})
            interaction['prompt'] = f'used fallback mechanism on current state: {json.dumps(self.state)}'
            utils.add_to_transcript(interaction, config)
            return json.dumps({"next action": "stop"})
        
        if config['model']['chunk_filling'] =="dummy" or fb:
            if not all([self.state['fields'][f] == 'answered' for f in self.state['fields']]):
                action = "question_generation"
            else:
                action = "fill_validation"
            ret = {
                "next action": action
            }
            interaction['output'] = json.dumps(ret)
            interaction['prompt'] = f'used fallback mechanism on current state: {json.dumps(self.state)}'
            utils.add_to_transcript(interaction, config)
            return json.dumps(ret)
        else:
            prompt = self.prompts['chunk_filling']
            state_str = json.dumps(self.state)
            prompt = prompt.replace('[State]', state_str)
            messages = [
                {'role': 'system', 'content': ''},
                {'role': 'user', 'content': prompt}
            ]
            out = utils.make_api_call(messages, config['model']['chunk_filling'], config)
            span, out_trim = output_matching.match_output(out, 'cfil')
            if span is None:
                logging.warning('Output of CFM model did not match expected pattern:\n%s', out)
                messages[1]['content'] += ('\n\n The output needs to fit the following Regular Expression:\n ' 
                                            + output_matching.re_chunk_filling.pattern)
                config['temperature'] = config['high temp']
                out = utils.make_api_call(messages, config['model']['chunk_filling'], config)
                config['temperature'] = config['base temp']
                span, out_trim = output_matching.match_output(out, 'cfil')
                if span is None:
                    logging.warning('Output of CFM model did not match expected pattern AGAIN:\n%s\ngoing with fallback mechanism', out)
                    return self.call(config, fb = True)  
            interaction['output'] = out_trim
            interaction['prompt'] = messages[1]['content']
            utils.add_to_transcript(interaction, config)
            return out_trim
    
    def question_generation(self, config, fb = False):
        interaction = {'module': 'Question generator'}
        if config['model']['question_generation'] == "dummy" or fb:
            q = utils.find_question(self.chunk)
            if q['question'] is None:
                q['question'] = 'Would you like to add anything?'
            stringified = q['question']
            if q['options'] is not None:
                str_opts = ', '.join(q['options'])
                stringified += f'\nYour Options are : [{str_opts}]'
            ret = {
                "question": stringified,
                "fields": [q['field']]
            }
            interaction['output'] = json.dumps(ret)
            interaction['prompt'] = f'used fallback mechanism on current chunk: {json.dumps(self.chunk)}'
            utils.add_to_transcript(interaction, config)
            return json.dumps(ret)
        else:
            chunk_copy = copy.deepcopy(self.chunk)
            open_chunk = utils.get_unanswered(chunk_copy, self.state['fields'])
            if not open_chunk:
                # do not try to create a new question but instead go straight to validation
                return self.question_generation(config, True)
            prompt = self.prompts['question_generation']
            prompt = prompt.replace('[Insert 1]', json.dumps(open_chunk))
            # prompt = prompt.replace('[Insert 2]', json.dumps(self.info))
            messages = [
                {'role': 'system', 'content': ''},
                {'role': 'user', 'content': prompt}
            ]
            out = utils.make_api_call(messages, config['model']['question_generation'], config)
            span, out_trim = output_matching.match_output(out, 'qgen')
            if span is None:
                logging.warning('Output of questions_generation model did not match expected pattern:\n%s', out)
                messages[1]['content'] += ('\n\n The output needs to fit the following Regular Expression:\n ' 
                                            + output_matching.re_question_generation.pattern)
                config['temperature'] = config['high temp']
                out = utils.make_api_call(messages, config['model']['question_generation'], config)
                config['temperature'] = config['base temp']
                span, out_trim = output_matching.match_output(out, 'qgen')
                if span is None:
                    logging.warning('Output of question_generation model did not match expected pattern AGAIN:\n%s\ngoing with fallback mechanism', out)
                    return self.question_generation(config, fb = True)  
            interaction['output'] = out_trim
            interaction['prompt'] = messages[1]['content']
            utils.add_to_transcript(interaction, config)
            return out_trim


    def fill_validation(self, config, fb = False):
        interaction = {'module': 'Answer Validator'}
        if config['model']['fill_validation'] == "dummy" or fb:
            for key, val in self.state['fields'].items():
                if val == 'answered':
                    self.state['fields'][key] = 'validated'
            interaction['output'] = json.dumps(self.chunk)
            interaction['prompt'] = f'used fallback mechanism on extracted information: {json.dumps(self.info)} \n\nand chunk of form: {json.dumps(self.chunk)}'
            utils.add_to_transcript(interaction, config)
            return json.dumps(self.chunk)
        else:
            prompt = self.prompts['fill_validation']
            info = json.dumps(self.info)
            section = json.dumps(self.chunk)
            prompt = prompt.replace('[Insert 1]', section)	
            prompt = prompt.replace('[Insert 2]', info)	
            messages = [
                {'role': 'system', 'content': ''},
                {'role': 'user', 'content': prompt}
            ]
            out = utils.make_api_call(messages, config['model']['fill_validation'], config)
            span, out_trim = output_matching.match_output(out, 'fval')
            fail = False
            if span is None:
                fail = True
            elif not utils.check_likeness(self.chunk, json.loads(out_trim)):
                fail = True
            if fail:
                logging.warning('Output of fill_validation model did not match expected pattern:\n%s', out)
                messages[1]['content'] += ('\n\n The output needs to fit the following Regular Expression:\n ' 
                                            + output_matching.re_fill_validation.pattern)
                config['temperature'] = config['high temp']
                out = utils.make_api_call(messages, config['model']['fill_validation'], config)
                config['temperature'] = config['base temp']
                span, out_trim = output_matching.match_output(out, 'fval')
                fail = False
                if span is None:
                    fail = True
                elif not utils.check_likeness(self.chunk, json.loads(out_trim)):
                    fail = True
                if fail:
                    logging.warning('Output of fill_validation model did not match expected pattern AGAIN:\n%s\ngoing with fallback mechanism', out)
                    return self.fill_validation(config, fb = True)  
            new = json.loads(out_trim)
            for key in new:
                self.chunk[key] = new[key] 
            self.state = utils.update_cf_state(self.state, self.chunk)
            for field in self.state['fields']:
                if self.state['fields'][field] == 'answered':
                    self.state['fields'][field] = 'validated'
            interaction['output'] = out_trim
            interaction['prompt'] = messages[1]['content']
            utils.add_to_transcript(interaction, config)
            return out_trim


    def load_prompts(self):
        prompts = {}
        with open('prompt_blueprints.json', 'r') as f:
            bp_file_paths = json.load(f)
        for module in ['answer_parsing', 'chunk_filling', 'form_filling', 'fill_validation', 'question_generation']:
            with open(os.path.join('blueprints', bp_file_paths[module]), 'r') as f:
                prompts[module] = f.read()
        return prompts
    
    def get_last_qs(self, n=3):
        if not self.dialogue:
            return []
        only_qs = self.dialogue[::2]
        return only_qs[-n:]



    