import logging
from typing import List, Dict

from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate


logger = logging.getLogger(__name__)


class AnalyzerService:
    def __init__(self, llm: ChatOpenAI):
        self.llm = llm
        self.prompt = PromptTemplate(
            input_variables=["context", "few_shot", "query"],
            template=(
                "You are a rail control systems debugging expert.\n"
                "Use this context from rail docs: {context}\n\n"
                "Few-shot examples:\n{few_shot}\n\n"
                "Step 1: Identify the error in rail code {query}.\n"
                "Step 2: Reference relevant docs from context.\n"
                "Step 3: Suggest a fix with code snippet for rail environment.\n"
                "Keep response under 300 words."
            ),
        )

    def analyze(self, query: str, context: str, few_shot_examples: List[Dict]) -> str:
        try:
            few_shot_str = "\n".join(
                [f"Example Input: {ex.get('input','')}\nOutput: {ex.get('output','')}" for ex in few_shot_examples[:3]]
            )
            prompt = self.prompt.format(context=context, few_shot=few_shot_str, query=query)
            resp = self.llm.invoke(prompt)
            content = getattr(resp, "content", None)
            return content or str(resp)
        except Exception as e:
            logger.error(f"Analyzer error: {e}")
            return "Error analyzing rail debug."

