# objective

## theme

- LLM faithfulness, hallucination, sycophancy

## idea

Do models agree with user misconceptions because they are sycophantic, or because they are just lazy/predicting the next likely word?

- investigate whether shortcut reliance also occurs during conversational generation of answers instead of just icl

## Cue idea for MATH-500

See [CUE_IMPLEMENTATION.md](CUE_IMPLEMENTATION.md)

## datasets

- Use HuggingFaceH4/MATH-500 dataset
- Create a pool for 50 stories - and then make your code randomly pick one without repetition for each turn

## model evaluation

- use azureml://registries/azureml-alibaba/models/qwen3-32b/versions/1
- Qwen3 32B serverless endpoint


## experiments

### Experiment 1:

Pool of stories:
5 stories with 2 {wrong_answer_shortcut_cue}  in one story
5 stories with 3 {wrong_answer_shortcut_cue}  in one story
5 stories with 10 {wrong_answer_shortcut_cue}  in one story

Plot: 
X axis: no of times the  {wrong_answer_shortcut_cue} was in the story
Y axis: no of times the model took the shortcut 
