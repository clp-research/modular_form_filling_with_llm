To evaluate runs you need to place the entire folder that has been output (it has a numerical name and is in the `/ouput` directory) into `/eval/to_test/`.
You can only evaluate successful runs since all the outputs are required.
Once you have put all the runs you want to evaluate into `/eval/to_test/`, you can call

```
python eval/create_scores.py
```

to create the scores and output them as json. You will find the results in `/eval/results/`. Each evaluation will create a new file (with a numerical name) here and each run will be scored separately but there will also be an average over all scored runs.