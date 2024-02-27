from typing import Dict
import json
import logging
import openai
import os
from time import sleep
import re
import requests
import random

try:
    import src.output_matching as output_matching
    from src.api_secrets import API_KEY
except ImportError:
    try:
        import output_matching
        from api_secrets import API_KEY
    except ImportError as e:
        exit(e)
        
client = openai.OpenAI(api_key=API_KEY)


form_map = {
    'ss5': 'resources/ss5.json',
    'epa': 'resources/epa.json',
    'med': 'resources/med.json',
    'inv': 'resources/inv.json'
}


def call_openai(messages, config):
    try:
        response = client.chat.completions.create(
            model=config["openai_model"],
            messages = messages,
            temperature = config['temperature']
        )
    except (openai.APIError, openai.APIConnectionError) as e:
        logging.error('encountered critical error while calling OpenAI API %s', e)
        exit(e)
    # print("got a response, yay")
    answer = response.choices[0].message.content.strip()
    # answer = answer.replace('\'', '\"')
    answer = re.sub(r'(?<=\w)"(?=\w)', '\'', answer)
    return answer


def call_local(messages, config):
    base = "http://127.0.0.1:5000/"
    ass = "### Assistant"
    usr = "### User"
    if len(messages) == 2:
        prompt = messages[-1]["content"]
        prompt_wrap = f"{usr}:\n{prompt}\n\n{ass}:\n"
    else:
        l = len(messages)
        prompt_wrap = ""
        for i in range(1, l):
            if i % 2 == 1:
                prompt_wrap += f"{usr}:\n{messages[i]['content']}\n\n"
            else:
                prompt_wrap += f"{ass}:\n{messages[i]['content']}\n\n"
        prompt_wrap += f"{ass}:\n"
    try:
        response = requests.get(base + "llm", data = {"prompt": prompt_wrap, "temp": config["temperature"]}, timeout=900)
    except requests.exceptions.Timeout:
        print("Connection Timed out")
        return "  "
    except:
        logging.error('encountered critical error while calling the local model')
        print("could not get a response from the local server")
        exit(1)
    unpacked = response.json()
    try:
        answer = unpacked["generated"]
    except KeyError:
        logging.warning('No key "generated" found in response from server.')
        try:
            response = requests.get(base + "llm", data = {"prompt": prompt_wrap, "temp": config["temperature"]})
        except:
            logging.error('encountered critical error while calling the local model')
            print("could not get a response from the local server")
            exit(1)
        unpacked = response.json()
        try:
            answer = unpacked["generated"]
        except KeyError:
            logging.error("could not get a correct response from the server after two attemps. Closing run.")
            exit(1)

    no_prompt = answer.split(f"{ass}:")[-1]
    return no_prompt.strip()


def auto_user(question, config):
    with open('resources/user-profiles.json', 'r') as f:
        profiles = json.load(f)
    num_p = len(profiles)
    choice = random.randint(0,num_p-1)
    profile = profiles[choice]
    # create the prompt and call make_api_call
    with open(f'blueprints/user_{config["form"]}.txt', 'r') as f:
        prompt = f.read()
    prompt = prompt.replace('[Insert 1]', profile)
    prompt = prompt.replace('[Insert 2]', question)
    if config['form'] == 'epa':
        prompt = prompt.replace('[Insert 3]', "reporting an environmental violation")
    elif config['form'] == 'ss5':
        prompt = prompt.replace('[Insert 3]', "an application for a social security card")
    elif config['form'] == 'med':
        prompt = prompt.replace('[Insert 3]', "your medical history"),
    elif config['form'] == 'inv':
        prompt = prompt.replace('[Insert 3]', "new invention of yours")

    messages = [
        {'role': 'system', 'content': ''},
        {'role': 'user', 'content': prompt}
    ]
    config['temperature'] = config['high temp']
    out = make_api_call(messages, config['model']['user'], config)
    config['temperature'] = config['base temp']
    span, out_trim = output_matching.match_output(out, 'user')
    if span is None:
        logging.warning('Output of user model did not match expected pattern:\n%s', out)
        messages.extend([
            {'role': 'assistant', 'content': out},
            {'role': 'user', 'content': ('\n\n The output needs to fit the following Regular Expression:\n ' 
                                    + output_matching.re_user.pattern)}
        ])
        config['temperature'] = config['high temp']
        out = make_api_call(messages, config['model']['user'], config)
        config['temperature'] = config['base temp']
        span, out_trim = output_matching.match_output(out, 'user')
        if span is None:
            logging.warning('Output of user model did not match expected pattern AGAIN:\n%s\ngoing with fallback mechanism', out)
            return ' '
        
    ans = json.loads(out_trim)
    return ans['answer']

    

def make_api_call(messages, model, config):
    # print('INFO: making an API call')
    if model == "gpt":
        answer = call_openai(messages, config)
    elif model == "local":
        answer = call_local(messages, config)
    
    
    
    with open('last_response.txt', 'w') as f:
        try:
            f.write(answer)
        except UnicodeEncodeError as e:
            logging.error(f"encountered encoding error while writing last received response: {str(e)}")
    
    return answer


def init_dl_state():
    state = {
        "chunks": {},
        "last action": []
    }
    return state

def update_dm_state(manager):
    for name, cfm in manager.cf_managers.items():
        cf_state = cfm.state
        filled = []
        vals = []
        for cond in cf_state['fields'].values():
            if cond == 'validated':
                vals.append(True)
                filled.append(True)
            elif cond == 'filled':
                vals.append(False)
                filled.append(True)
            elif cond == 'partially filled':
                vals.append(False)
                filled.append(True)
                filled.append(False)
            elif cond == 'empty':
                vals.append(False)
                filled.append(False)
        if all(vals):
            manager.state['chunks'][name] = 'validated'
        elif all(filled) and any(vals):
            manager.state['chunks'][name] = 'partially validated'
        elif all(filled):
            manager.state['chunks'][name] = 'filled'
        elif any(filled):
            manager.state['chunks'][name] = 'partially filled'
        elif not any(filled):
            manager.state['chunks'][name] = 'empty'

    return manager

def load_form(name):
    path = form_map[name]
    with open(path, 'r') as f:
        form = json.load(f)
    return form

def init_cf_state(chunk):
    fields = {lbl: "empty" for lbl in chunk}
    state = {
        "fields": fields,
        "last action": [],
        "last question": None
    }
    return state

def load_config(path):
    with open(path, 'r') as f:
        config = json.load(f)
    return config

def find_question(part: Dict) -> Dict:
    q = {
        'question': None,
        'options': None,
        'field': ""
    }
    if not isinstance(part, dict):
        logging.warning("wrong datatype was passed to `find_question`")
        return q
    for key, value in part.items():
        if isinstance(value, dict):
            if 'answer' in value.keys():
                if value['answer'] is None:
                    q['question'] = key
                    q['field'] = key
                    if 'options' in value.keys():
                        q['options'] = value['options']
                    return q
            q = find_question(value)
            if q['question'] is not None:
                return q
    return q

def find_and_fill(chunk, info):
    for key in info:
        path = key.split(':')
        if key in chunk.keys():
            if isinstance(chunk[key], dict):
                if 'answer' in chunk[key].keys():
                    chunk[key]['answer'] = info[key]
                    return chunk
        if len(path) > 1:
            new_path = ':'.join(path[1:])
            step = path[0]
            if not step in chunk.keys():
                continue
            chunk[step] = find_and_fill(chunk[step], {new_path: info[key]})
    return chunk


def update_cf_state(state, chunk):
    for key in state['fields'].keys():
        if state['fields'][key] == 'validated':
            continue
        answered = search(chunk[key], [])
        # print(answered)
        if all(answered):
            state['fields'][key] = 'answered'
        elif any(answered):
            state['fields'][key] = 'partially answered'
        else:
            state['fields'][key] = 'empty'

    return state


def search(chunk, answered):
    if not isinstance(chunk, dict):
        return answered
    ks = chunk.keys()
    if  'answer' in ks and 'required' in ks:
        if chunk['required']:
            if chunk['answer'] is None or chunk['answer'] == '':
                answered.append(False)
            else:
                answered.append(True)
    else:
        for k in ks:
            answered += search(chunk[k], [])
    return answered

def get_out_dir():
    dirs = os.listdir('output')
    try:
        dirs = dirs.remove('.ipynb_checkpoints')
    except:
        pass
    int_dirs = [int(d) for d in dirs]
    if int_dirs:
        path =  f'output/{str(max(int_dirs)+1)}'
    else:
        path = 'output/1'
    os.mkdir(path)
    return path

def add_to_transcript(interaction, config):
    path = os.path.join(config['out_dir'], 'transcript.json')
    if not os.path.isfile(path):
        with open(path, 'w') as f:
            to_dump = {"interactions": []}
            json.dump(to_dump, f)
    with open(path, 'r') as f:
        transcript_json = json.load(f)
    transcript_json['interactions'].append(interaction)
    with open(path, 'w') as f:
        json.dump(transcript_json, f)
    return 1


def check_likeness(old, new):
    if not isinstance(old, dict) or not isinstance(new, dict):
        return False
    old_keys = list(old.keys())
    new_keys = list(new.keys())
    if old_keys and not new_keys:
        return False
    for k in new_keys:
        if k not in old_keys:
            return False
    for key in new_keys:
        if key == 'answer':
            continue
        if not key in old_keys:
            return False
        if isinstance(old[key], dict) and isinstance(new[key], dict):
            if not check_likeness(old[key], new[key]):
                return False
        elif type(old[key]) != type(new[key]):
            return False
    return True


def get_unanswered(chunk, state):
    ret = {}
    for key in state:
        if state[key] in ['answered', 'validated']:
            continue
        ret[key] = chunk[key]
    return ret


def rec_del_answered(chunk):
    if not isinstance(chunk, dict):
        return chunk
    ks = list(chunk.keys())
    for key in ks:
        if isinstance(chunk[key], dict):
            if 'answer' in chunk[key].keys():
                if chunk[key]['answer'] is not None:
                    del chunk[key]
            else:
                chunk[key] = rec_del_answered(chunk[key])
    return chunk
  



def get_working_fields(fields, chunk):
    ret = {}
    for field in fields:
        top_lvl = field.split(':')[0]
        part = chunk.get(top_lvl, None)
        if part is None:
            logging.warning('qgen suggested to work on %s, but this is not part of the current chunk', field)
            continue
        ret[top_lvl] = part
    return ret


def fill_in_parts(chunk, filled):
    if not isinstance(chunk, dict) and not isinstance(filled, dict):
        logging.error('encountered wrong datatype in fill_in_parts')
        return chunk
    if 'answer' in filled.keys():
        chunk['answer'] = filled['answer']
        return chunk
    for key in filled:
        if not key in chunk.keys():
            continue
        if isinstance(filled[key], dict):
            chunk[key] = fill_in_parts(chunk[key], filled[key])  
    return chunk

def check_specials(config):
    if config.get("special_mode", -1) == -1:
        return config
    if config["special_mode"] == 'all_gpt':
        for key in config['model']:
            config['model'][key] = "gpt"
    elif config["special_mode"] == 'all_local':
        for key in config['model']:
            config['model'][key] = "local"
    elif config["special_mode"] == 'all_dummy':
        for key in config['model']:
            config['model'][key] = "dummy"
    return config

def check_grouping(grp, form, sums):
    sums = json.loads(sums)
    try:
        groupings = json.loads(grp)
    except json.decoder.JSONDecodeError:
        logging.warning('could not read the returned data from question grouping')
        return None
    if not isinstance(groupings, dict):
        logging.warning('question grouping returned in wrong format')
        return None
    keys = list(groupings.keys())
    sum_keys = list(sums.keys())
    sum_vals = list(sums.values())
    for key in keys:
        if not isinstance(groupings[key], list):
            logging.warning('question grouping returned in wrong format (list)')
            return None
        for i, entry in enumerate(groupings[key]):
            if entry in sum_keys:
                continue
            elif entry in sum_vals:
                for k in sums:
                    if sums[k] == entry:
                        groupings[key][i] = k
            else:
                logging.warning('grouping had entry from neither summaries or summary keys')
                return None
    return json.dumps(groupings)