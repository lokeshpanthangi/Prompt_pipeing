"""
Prompt generator for automated prompt optimization.
Generates improved prompts based on failure analysis.
"""

import json
import logging
import random
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class PromptGenerator:
    """Generates optimized prompts based on performance failures."""
    
    def __init__(self, client, config: Optional[Dict] = None):
        """Initialize prompt generator."""
        self.client = client
        self.config = config or {
            "max_variants": 5,
            "optimization_strategies": ["clarity", "specificity", "examples", "structure"]
        }
        self.prompt_history = []
    
    async def generate_optimized_prompts(self, failure_report: Dict, original_prompts: Dict) -> Dict:
        """Generate optimized prompts based on failure analysis."""
        optimization_plan = {
            "timestamp": datetime.now().isoformat(),
            "failure_analysis": failure_report,
            "optimization_strategy": self._select_optimization_strategy(failure_report),
            "original_prompts": original_prompts,
            "optimized_prompts": {},
            "generation_method": "automated"
        }
        
        # Generate optimized prompts for each problem type
        for problem_type in ["math", "logic", "code", "general"]:
            if problem_type in original_prompts:
                optimized = await self._optimize_prompts_for_type(
                    problem_type, original_prompts[problem_type], failure_report
                )
                optimization_plan["optimized_prompts"][problem_type] = optimized
        
        # Save to history
        self.prompt_history.append(optimization_plan)
        
        logger.info(f"Generated optimized prompts using strategy: {optimization_plan['optimization_strategy']}")
        return optimization_plan
    
    def _select_optimization_strategy(self, failure_report: Dict) -> str:
        """Select optimization strategy based on failure patterns."""
        failure_reasons = failure_report.get("failure_patterns", {}).get("reasons", {})
        
        # Analyze failure patterns to choose strategy
        if "Low confidence" in str(failure_reasons):
            return "confidence_boosting"
        elif "Empty or too short answer" in str(failure_reasons):
            return "response_encouragement"
        elif "Low accuracy" in str(failure_reasons):
            return "accuracy_improvement"
        else:
            return "general_enhancement"
    
    async def _optimize_prompts_for_type(self, problem_type: str, original_prompts: Dict, 
                                       failure_report: Dict) -> Dict:
        """Optimize prompts for a specific problem type."""
        strategy = self._select_optimization_strategy(failure_report)
        
        optimized_prompts = {}
        
        # Optimize Tree-of-Thought prompts
        if "tree_of_thought" in original_prompts:
            tot_prompts = original_prompts["tree_of_thought"]
            optimized_prompts["tree_of_thought"] = await self._optimize_tot_prompts(
                tot_prompts, problem_type, strategy
            )
        
        # Optimize Self-Consistency prompts
        if "self_consistency" in original_prompts:
            sc_prompts = original_prompts["self_consistency"]
            optimized_prompts["self_consistency"] = await self._optimize_sc_prompts(
                sc_prompts, problem_type, strategy
            )
        
        return optimized_prompts
    
    async def _optimize_tot_prompts(self, original_prompts: Dict, problem_type: str, 
                                  strategy: str) -> Dict:
        """Optimize Tree-of-Thought prompts."""
        optimized = {}
        
        for approach in ["analytical", "intuitive", "systematic", "creative", "verification"]:
            if approach in original_prompts:
                original_prompt = original_prompts[approach]
                optimized_prompt = await self._apply_optimization_strategy(
                    original_prompt, strategy, f"{problem_type}_{approach}"
                )
                optimized[approach] = optimized_prompt
        
        return optimized
    
    async def _optimize_sc_prompts(self, original_prompts: Dict, problem_type: str, 
                                 strategy: str) -> Dict:
        """Optimize Self-Consistency prompts."""
        optimized = {}
        
        if "base_prompt" in original_prompts:
            original_prompt = original_prompts["base_prompt"]
            optimized_prompt = await self._apply_optimization_strategy(
                original_prompt, strategy, f"{problem_type}_consistency"
            )
            optimized["base_prompt"] = optimized_prompt
        
        # Generate variations
        if "variations" in original_prompts:
            original_variations = original_prompts["variations"]
            optimized_variations = []
            
            for i, variation in enumerate(original_variations[:3]):  # Optimize top 3
                optimized_variation = await self._apply_optimization_strategy(
                    variation, strategy, f"{problem_type}_variation_{i}"
                )
                optimized_variations.append(optimized_variation)
            
            optimized["variations"] = optimized_variations
        
        return optimized
    
    async def _apply_optimization_strategy(self, original_prompt: str, strategy: str, 
                                         context: str) -> str:
        """Apply specific optimization strategy to a prompt."""
        optimization_prompt = self._build_optimization_prompt(original_prompt, strategy, context)
        
        try:
            response = await self.client.generate_single(optimization_prompt)
            
            if "error" in response:
                logger.warning(f"Error optimizing prompt: {response['error']}")
                return self._fallback_optimization(original_prompt, strategy)
            
            optimized_prompt = response["text"].strip()
            
            # Validate the optimized prompt
            if self._validate_optimized_prompt(optimized_prompt, original_prompt):
                return optimized_prompt
            else:
                return self._fallback_optimization(original_prompt, strategy)
                
        except Exception as e:
            logger.error(f"Error in prompt optimization: {str(e)}")
            return self._fallback_optimization(original_prompt, strategy)
    
    def _build_optimization_prompt(self, original_prompt: str, strategy: str, context: str) -> str:
        """Build the meta-prompt for optimizing prompts."""
        strategy_instructions = {
            "confidence_boosting": "Make the prompt encourage more confident and decisive responses. Add phrases that boost model confidence.",
            "response_encouragement": "Modify the prompt to encourage longer, more detailed responses. Add explicit instructions for thorough explanations.",
            "accuracy_improvement": "Enhance the prompt to improve accuracy. Add verification steps and double-checking instructions.",
            "general_enhancement": "Improve the prompt for better clarity, specificity, and effectiveness."
        }
        
        instruction = strategy_instructions.get(strategy, strategy_instructions["general_enhancement"])
        
        return f"""You are an expert prompt engineer. Your task is to optimize the following prompt for better performance.

CONTEXT: {context}
OPTIMIZATION GOAL: {instruction}

ORIGINAL PROMPT:
{original_prompt}

Please provide an improved version of this prompt that addresses the optimization goal. 
Keep the core intent and structure, but enhance it for better results.
Return only the optimized prompt without explanations.

OPTIMIZED PROMPT:"""
    
    def _validate_optimized_prompt(self, optimized: str, original: str) -> bool:
        """Validate that the optimized prompt is reasonable."""
        # Basic validation checks
        if not optimized or len(optimized) < 20:
            return False
        
        if len(optimized) > len(original) * 3:  # Too long
            return False
        
        # Check that it's still a prompt-like structure
        if "?" not in optimized and ":" not in optimized:
            return False
        
        return True
    
    def _fallback_optimization(self, original_prompt: str, strategy: str) -> str:
        """Provide fallback optimization when AI optimization fails."""
        fallback_improvements = {
            "confidence_boosting": {
                "prefixes": ["You are confident that", "You can definitively determine that"],
                "suffixes": ["Provide your most confident answer.", "Be decisive in your response."]
            },
            "response_encouragement": {
                "prefixes": ["Provide a detailed explanation for"],
                "suffixes": ["Explain your reasoning step by step.", "Show your complete thought process."]
            },
            "accuracy_improvement": {
                "prefixes": ["Carefully analyze and solve"],
                "suffixes": ["Double-check your answer before responding.", "Verify your solution is correct."]
            },
            "general_enhancement": {
                "prefixes": ["Thoughtfully consider"],
                "suffixes": ["Provide a clear and accurate response."]
            }
        }
        
        improvements = fallback_improvements.get(strategy, fallback_improvements["general_enhancement"])
        
        # Simple enhancement by adding prefix/suffix
        prefix = random.choice(improvements.get("prefixes", [""]))
        suffix = random.choice(improvements.get("suffixes", [""]))
        
        if prefix and not original_prompt.startswith(prefix):
            enhanced = f"{prefix} {original_prompt.lower()}"
        else:
            enhanced = original_prompt
        
        if suffix and not enhanced.endswith(suffix):
            enhanced = f"{enhanced} {suffix}"
        
        return enhanced
    
    def get_optimization_history(self) -> List[Dict]:
        """Get history of prompt optimizations."""
        return self.prompt_history
    
    def save_optimization_history(self, filepath: str):
        """Save optimization history to file."""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(self.prompt_history, f, indent=2)
        
        logger.info(f"Optimization history saved to {filepath}")
    
    def load_optimization_history(self, filepath: str):
        """Load optimization history from file."""
        try:
            with open(filepath, 'r') as f:
                self.prompt_history = json.load(f)
            logger.info(f"Optimization history loaded from {filepath}")
        except FileNotFoundError:
            logger.info(f"No optimization history found at {filepath}")
        except Exception as e:
            logger.error(f"Error loading optimization history: {str(e)}") 