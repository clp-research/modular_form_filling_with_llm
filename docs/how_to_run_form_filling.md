# How to run Form Filling 

## Setting up

The first thing you will need to do is to set your Openai API key and install all necessary requirements. 

### Setting your Openai API key

Create the file `src/api_secrets.py` which is identical in content to `src/api_secrets(template).py`. Then put your own API key as the `API_KEY` variable in this file.

### Installing Requirements

All necessary requirements can be installed using 

```
pip install -r requirements.txt
```

## Running the system

### OpenAI

At this point you may already run the system using the Openai API only.
You can edit parameters and models in [config.json](../config/config.json). If you are running exclusively OpenAI models set the model for all components to `gpt` or setting `"special_mode": "all_gpt"`. 

In the same config file you may also chose to change the generation temperature, both for regular generation calls and fallback generation (when the initial generation has failed, it may help to generate with a higher temperature). These values are denoted as `base_temp` and `high_temp` respectively. 

Additionally, you may chose whether you want to simulate the User or enter answers yourself. The User will be simulated if you set `autouser` to `true`. 

You also need to chose the form that is supposed to be filled out here. The repository comes with 4 forms, as described in the paper, but you may add additional ones. Instructions on how to add a new form can be seen in [how_to_add_forms](how_to_add_forms.md). 

Without adding your own form you may set the parameter to be one of the following values: `ss5`, `epa`, `med` or `inv`.

Once you've set the config to the desired values, you may run the system by using the following command:

```
python src/main.py
```

### Huggingface Transformers

In order to run open-access Huggingface models, you will need to host the model on a server. A simple script is provided with this repository that will host any given model on a local flask server.

Choose your model and enter it's Huggingface id in the name field in [server/server_config.yaml](../server/server_config.yaml). You can then start the server by calling 

```
python server/llm_server.py
```

You may test if the server is running successfully by calling the test script

```
python server/test_server.py
```

Once the server is running, you can use it by setting the model for modules of the system in [config.json](../config/config.json) to `local` or set `"special_mode": "all_local"`.
You may also mix OpenAI and Huggingface models in the same run if you want.

Again, run the system by calling 

```
python src/main.py
```

### Results

A folder with a numerical name will be created in the `output` directory where, after successful completion, you will find:

- `"cfm-states.json"` - the current states for all Chunk Filler modules
- `"config.json"` - the configuration you ran the experiment with
- `"dialogue.json"` - The messages being passed between user and system
- `"dm-state.json"` - the current state of the Dialogue Manager
- `"filled-form.json"` - the filled out form
- `"info.json"` - the information that has been extracted from the dialogue by the system
- `"transcript.json"` - A log of all interactions, primarily used for scoring

To see how you can score you own run, see [how_to_eval.md](how_to_eval.md). There are already transcripts of completed runs stored in [result_store](../result_store).