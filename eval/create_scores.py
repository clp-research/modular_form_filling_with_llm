import os
import json
import numpy as np

def make_result_dir():
    root = 'eval/results'
    dirs = os.listdir(root)
    tmp = []
    for d in dirs:
        try:
            i = int(d)
            tmp.append(i)
        except ValueError:
            pass
    int_dirs = tmp
    if int_dirs:
        path =  f'{root}/{str(max(int_dirs)+1)}'
    else:
        path = f'{root}/1'
    os.mkdir(path)
    return path

def get_to_test():
    root = "eval/to_test"
    dirs = os.listdir(root)
    dirs.remove("Readme.md")
    return [f"{root}/{dir}" for dir in dirs]

def load_config():
    with open('eval/test_config.json', 'r') as f:
        config = json.load(f)
    return config

def run_tests(paths, config):
    results = {}
    for path in paths:
        results[path] = test_run(path, config)
    return results

def test_run(path, config):
    results = {
        "length": 0,
        "reps": 0,
        "turns": 0,
        "user_questions": 0,
        "invalid_answers": 0,
        "obl. fields": 0,
        "opt. fields": 0,
        "filled obl. fields": 0,
        "filled opt. fields": 0,
        "successes": 0,
        "failures": 0
    }
    # success test
    try:
        with open(f"{path}/filled-form.json", "r") as f:
            form = json.load(f)
        # results['success'] = determine_success(form)
        results['length'] = form_length(form)

        fields = num_fields(form)
        results['obl. fields'] = int(fields[0])
        results['opt. fields'] = int(fields[1])
        results['filled obl. fields'] = int(fields[2])
        results['filled opt. fields'] = int(fields[3])
    except (FileExistsError, FileNotFoundError) as e:
        print('error in ', f"{path}/filled-form.json")
        print(e)
    except KeyError as e:
        print('error in ', f"{path}/filled-form.json")
        print(e)

    # repetition count, user interactions
    try:
        with open(f"{path}/dialogue.json", "r") as f:
            dialogue = json.load(f)
        results['reps'] = repetition_count(dialogue)
        results['turns'] = int(len(dialogue)/2)
        results['user_questions'] = user_questions(dialogue)
    except (FileExistsError, FileNotFoundError) as e:
        print('error in ', f"{path}/dialogue.json")
        print(e)


    try:
        with open(f"{path}/transcript.json", "r") as f:
            transcript = json.load(f)
        successes, failures = get_succ(transcript)
        results['successes'] = successes
        results['failures'] = failures
    except (FileExistsError, FileNotFoundError) as e:
        print('error in ', f"{path}/transcript.json")
        print(e)

    return results


def get_succ(t):
    succs = 0
    fails = 0
    t = t['interactions']
    for i in range(1, len(t)):
        if t[i]['module'] == "user":
            if t[i+2]['module'] == "information_extraction":
                succs += 1
            else:
                fails += 1
    return succs, fails
        

def num_fields(form):
    nums = np.array((0,0,0,0)) # (obl. fields, opt. fields, filled obl. fields, filled opt. fields)
    if not isinstance(form, dict):
        return (0,0,0,0) # went too deep, nothing to find here
    if 'answer' in form.keys() and 'required' in form.keys():
        if form['required']:
            try:
                if form['answer'] is not None and form['answer'] != "":
                    return (1,0,1,0)
                else:
                    return (1,0,0,0)
            except KeyError:
                pass
        elif not form['required']:
            try:
                if form['answer'] is not None and form['answer'] != "":
                    return (0,1,0,1)
                else:
                    return (0,1,0,0)
            except KeyError:
                pass
    for key in form:
        if isinstance(form[key], dict):
            nums += num_fields(form[key])
    return nums

def invalids_passed(form):
    num = 0
    if not isinstance(form, dict):
        return 0 # went too deep, nothing to find here
    if 'type' in form.keys():
        if form['type'] == 'checkbox':
            try:
                if form['answer'] not in form['options']:
                    return 1
                else:
                    return 0
            except KeyError:
                pass
        if form['type'] == 'multi-choice':
            
            try:
                if isinstance(form['answer'], str):
                    if form['answer'] not in form['options']:
                        return 1
                    return 0
                elif isinstance(form['answer'], list):
                    for ans in form['answer']:
                        if ans not in form['options']:
                            return 1
                    return 0
            except KeyError:
                pass
    for key in form:
        if isinstance(form[key], dict):
            num += invalids_passed(form[key])
    return num

def user_questions(dialogue):
    num = 0
    for entry in dialogue:
        if 'User' in entry.keys():
            if '?' in entry['User']:
                num += 1
    return num

def write_results(results, path, config):
    averages = {
        "length": 0,
        "reps": 0,
        "turns": 0,
        "user_questions": 0,
        "invalid_answers": 0,
        "obl. fields": 0,
        "opt. fields": 0,
        "filled obl. fields": 0,
        "filled opt. fields": 0,
        "successes": 0,
        "failures": 0
    }
    keys = list(results.keys())
    l = len(keys)
    for key in keys:
        for k in averages.keys():
            averages[k] += int(results[key][k])

    for key in averages.keys():
        averages[key] /= l

    results['avg'] = averages

    with open(f"{path}/results.json", 'w') as f:
        json.dump(results, f)
    

def determine_success(form):
    """A form has been successfully filled out if all required fields have been filled out.
    This does not mean all fields need to be filled out or that the results make sense.
    This is not a qualitative measure. This just means the process ran from start to finish.

    Args:
        form (dict): form or part of form to check

    Returns:
        success (bool): has the process been successful or not
    """

    if not isinstance(form, dict):
        return True # went too deep, nothing to find here
    if 'answer' in form.keys():
        if form.get('required', False):
            if form['answer'] is None:
                return False # there is an answer which is required but not filled out
            else:
                return True # there is an answer which is required and filled out
        else:
            return True # there is an answer which is not required
    for key in form:
        if isinstance(form[key], dict):
            if not determine_success(form[key]): # there is not answer, so go deeper
                return False # recursive call found an error
    return True # went through the entire form without finding an error


def form_length(form):
    num = 0
    if not isinstance(form, dict):
        return 0 # went too deep, nothing to find here
    if 'answer' in form.keys():
        return 1
    for key in form:
        if isinstance(form[key], dict):
            num += form_length(form[key])
    return num
    
def repetition_count(dialogue):
    """counts how often a question has been repeated by the system.

    Args:
        dialogue (list): each list entry is a dict with either "Assistant" or "User" as a key.

    Returns:
        int: number of repeated questions
    """
    reps = 0
    said = []
    for entry in dialogue:
        if "Assistant" in entry.keys():
            if entry["Assistant"] in said:
                reps += 1
            else:
                said.append(entry["Assistant"])
    return reps



if __name__ == "__main__":
    config = load_config()
    result_path = make_result_dir()
    test_paths = get_to_test()
    results = run_tests(test_paths, config)
    write_results(results, result_path, config)
