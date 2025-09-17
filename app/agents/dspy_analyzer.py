# app/agents/dspy_analyzer.py
import dspy

# 1. Define the signature for the task
class GenerateRailFix(dspy.Signature):
    """Analyze the rail code issue based on context and suggest a fix with a code snippet."""
    context = dspy.InputField(desc="Relevant snippets from rail documentation.")
    query = dspy.InputField(desc="The user's debugging query, including an error message or code.")
    fix = dspy.OutputField(desc="A concise, actionable fix including a corrected code snippet.")

# 2. Define the DSPy module
class DSPyRAG(dspy.Module):
    def __init__(self):
        super().__init__()
        # ChainOfThought encourages the LLM to reason before answering
        self.generate_answer = dspy.ChainOfThought(GenerateRailFix)

    def forward(self, query, context):
        prediction = self.generate_answer(context=context, query=query)
        return prediction

# In a separate script, you would run the optimization:
# from dspy.teleprompt import BootstrapFewShot
#
# # Configure DSPy settings (e.g., the LLM to use for optimization)
# turbo = dspy.OpenAI(model='gpt-3.5-turbo')
# dspy.settings.configure(lm=turbo)
#
# # Define your metric
# def validation_metric(example, prediction, trace=None):
#     # Returns True if the prediction is good, False otherwise
#     # This could check for code validity, keyword presence, etc.
#     return "valid_code_keyword" in prediction.fix and example.golden_fix in prediction.fix
#
# # Set up the optimizer
# config = dict(max_bootstrapped_demos=4, max_labeled_demos=4)
# teleprompter = BootstrapFewShot(metric=validation_metric, **config)
#
# # Compile (optimize) the DSPy program
# optimized_rag = teleprompter.compile(DSPyRAG(), trainset=your_training_set)