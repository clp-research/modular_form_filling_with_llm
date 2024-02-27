import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from flask import Flask, request
from flask_restful import Api, Resource
import yaml

with open("server/server_config.yaml", 'r') as f:
    conf = yaml.safe_load(f)

app = Flask(__name__)
api = Api(app)

HF_CACHE = conf['cache']

NAME = conf['name']

tokenizer = AutoTokenizer.from_pretrained(NAME, cache_dir = HF_CACHE)
model = AutoModelForCausalLM.from_pretrained(
    NAME,
    device_map=0,
    torch_dtype=torch.float16,
    load_in_8bit=True,
    rope_scaling={"type": "dynamic", "factor": 2}, # allows handling of longer inputs
    cache_dir = HF_CACHE
)

device = torch.device('cuda')

class LLM(Resource):
    def get(self):
        prompt = request.form['prompt']
        temp = request.form['temp']
        prompt = f"{prompt}\n"
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            output = model.generate(**inputs, use_cache=False, max_new_tokens=float('inf'), temperature = temp)
        output_text = tokenizer.decode(output[0], skip_special_tokens=True)
        print(output_text)
        return {"generated": output_text}
    

api.add_resource(LLM, "/llm")

if __name__ == "__main__":
    
    app.run(debug=conf['debug'])