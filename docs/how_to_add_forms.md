To add a form you will need to convert it to json format and follow the structure of the other forms in this repository.

It is important that each field has the following tags:

* `type` - What kind of field it is. In past forms this was either `text-field`, `single-choice` or `multi-choice`
* `required` - This is a boolean and denotes whether this is a required fields or not
* `answer` - If this can be answered it needs a answer field. This should be set to `null` initially.

There are some additional tags you may add to appropriate fields.

* `options` - If the field is of type `single-choice` or `multi-choice`, provide all answer options here.
* `info` - if additional information is provided with the field, add it in here. 

Now add this new form to the others in `/resources/` and name it fittingly, e.g. `your_form_name.json`. You will also need to add this form into the dictionary at the top of [utils.py](../src/utils.py). Add an entry like this: `"short_name": "your_form_name.json"`.

You can now run the system on this new form by setting `"form": "short_name"` in [config.json](../config/config.json).