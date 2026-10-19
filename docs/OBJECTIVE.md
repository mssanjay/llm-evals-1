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
- run Qwen and DeepSeek
- compare reasoning off and reasoning on after a two-call reasoning-field check


## experiments

### Experiment 1:

- Condition 1: teaching story number = wrong cue = scripted assistant answer
- Condition 2: teaching story number = gold = scripted assistant answer
- Probe for both conditions: new problem with a wrong cue
- 45 shared probe episodes with 15 episodes per shortcut cue type
- Three shortcut cue types: plus one, times ten, and deterministic random

Pool of stories:
5 stories with 1 {wrong_answer_shortcut_cue}  in one story
5 stories with 2 {wrong_answer_shortcut_cue}  in one story
5 stories with 3 {wrong_answer_shortcut_cue}  in one story
5 stories with 4 {wrong_answer_shortcut_cue}  in one story
5 stories with 5 {wrong_answer_shortcut_cue}  in one story
5 stories with 6 {wrong_answer_shortcut_cue}  in one story
5 stories with 7 {wrong_answer_shortcut_cue}  in one story
5 stories with 8 {wrong_answer_shortcut_cue}  in one story
5 stories with 9 {wrong_answer_shortcut_cue}  in one story
5 stories with 10 {wrong_answer_shortcut_cue}  in one story


Plot: 
X axis: no of times the  {wrong_answer_shortcut_cue} was in the story
Y axis: no of times the model took the shortcut 
