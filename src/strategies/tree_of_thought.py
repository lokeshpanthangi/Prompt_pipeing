"""
Tree-of-Thought (ToT) strategy implementation for multi-path reasoning.
Generates multiple reasoning paths and evaluates their quality.
"""

from typing import List, Dict, Optional, Tuple
import asyncio
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TreeOfThought:
    """Tree-of-Thought reasoning strategy using Gemini 1.5 Flash."""
    
    def __init__(self, gemini_client, config: Optional[Dict] = None):
        """Initialize ToT with Gemini client and configuration."""
        self.client = gemini_client
        self.config = config or {}
        self.max_paths = self.config.get("max_paths", 5)
        self.evaluation_threshold = self.config.get("path_evaluation_threshold", 0.6)
    
    async def generate_reasoning_paths(self, problem: str, problem_type: str = "general") -> List[Dict]:
        """Generate multiple reasoning paths for the given problem."""
        logger.info(f"Generating {self.max_paths} reasoning paths for problem type: {problem_type}")
        
        # Create different reasoning prompts
        path_prompts = self._create_reasoning_prompts(problem, problem_type)
        
        # Generate paths in parallel
        path_results = await self.client.generate_multiple(path_prompts)
        
        # Process and evaluate paths
        reasoning_paths = []
        for i, result in enumerate(path_results):
            if "error" not in result:
                path = {
                    "path_id": i,
                    "reasoning_type": self._get_reasoning_type(i),
                    "prompt": result["prompt"],
                    "response": result["text"],
                    "timestamp": result["timestamp"],
                    "quality_score": 0.0,  # Will be calculated
                    "final_answer": self._extract_final_answer(result["text"]),
                    "reasoning_steps": self._extract_reasoning_steps(result["text"])
                }
                reasoning_paths.append(path)
            else:
                logger.warning(f"Error in path {i}: {result['error']}")
        
        # Evaluate path quality
        evaluated_paths = await self._evaluate_path_quality(reasoning_paths)
        
        # Sort by quality score
        evaluated_paths.sort(key=lambda x: x["quality_score"], reverse=True)
        
        logger.info(f"Generated {len(evaluated_paths)} valid reasoning paths")
        return evaluated_paths
    
    def _create_reasoning_prompts(self, problem: str, problem_type: str) -> List[str]:
        """Create different types of reasoning prompts."""
        base_prompts = {
            "analytical": self._create_analytical_prompt(problem, problem_type),
            "intuitive": self._create_intuitive_prompt(problem, problem_type),
            "systematic": self._create_systematic_prompt(problem, problem_type),
            "creative": self._create_creative_prompt(problem, problem_type),
            "verification": self._create_verification_prompt(problem, problem_type)
        }
        
        return list(base_prompts.values())[:self.max_paths]
    
    def _create_analytical_prompt(self, problem: str, problem_type: str) -> str:
        """Create analytical reasoning prompt."""
        templates = {
            "math": f"""
            Solve this mathematical problem using analytical reasoning:
            
            Problem: {problem}
            
            Approach:
            1. Identify all given information and what needs to be found
            2. Determine the mathematical concepts and formulas needed
            3. Set up equations or relationships
            4. Solve step by step with clear calculations
            5. Verify your answer makes sense
            
            Show all work and reasoning:
            """,
            
            "logic": f"""
            Analyze this logical problem systematically:
            
            Problem: {problem}
            
            Approach:
            1. Identify the logical structure and premises
            2. Determine what type of logical reasoning is needed
            3. Apply logical rules and principles
            4. Draw conclusions step by step
            5. Check for logical consistency
            
            Show your logical reasoning:
            """,
            
            "code": f"""
            Analyze this code problem methodically:
            
            Problem: {problem}
            
            Approach:
            1. Understand the code structure and purpose
            2. Identify potential issues or optimization opportunities
            3. Trace through the execution flow
            4. Apply programming principles and best practices
            5. Propose solutions with explanations
            
            Show your analysis:
            """,
            
            "general": f"""
            Analyze this problem using structured reasoning:
            
            Problem: {problem}
            
            Approach:
            1. Break down the problem into components
            2. Identify relevant principles and knowledge
            3. Apply systematic thinking
            4. Build solution step by step
            5. Validate the reasoning
            
            Show your analytical approach:
            """
        }
        
        return templates.get(problem_type, templates["general"])
    
    def _create_intuitive_prompt(self, problem: str, problem_type: str) -> str:
        """Create intuitive reasoning prompt."""
        return f"""
        Solve this problem using intuitive reasoning and pattern recognition:
        
        Problem: {problem}
        
        Approach:
        - Look for patterns and familiar structures
        - Use intuition and common sense
        - Apply heuristics and shortcuts where appropriate
        - Think about what feels right based on experience
        - Verify intuitive leaps with quick checks
        
        Trust your instincts and show your thinking:
        """
    
    def _create_systematic_prompt(self, problem: str, problem_type: str) -> str:
        """Create systematic reasoning prompt."""
        return f"""
        Solve this problem using a systematic, methodical approach:
        
        Problem: {problem}
        
        Method:
        1. Define the problem clearly
        2. List all constraints and requirements
        3. Consider all possible approaches
        4. Choose the most promising method
        5. Execute the solution systematically
        6. Double-check each step
        
        Be thorough and methodical:
        """
    
    def _create_creative_prompt(self, problem: str, problem_type: str) -> str:
        """Create creative reasoning prompt."""
        return f"""
        Approach this problem creatively and explore alternative solutions:
        
        Problem: {problem}
        
        Creative approach:
        - Think outside conventional methods
        - Consider multiple perspectives
        - Look for unexpected connections
        - Try different solution strategies
        - Be innovative while maintaining accuracy
        
        Show your creative reasoning:
        """
    
    def _create_verification_prompt(self, problem: str, problem_type: str) -> str:
        """Create verification-focused reasoning prompt."""
        return f"""
        Solve this problem with extra focus on verification and checking:
        
        Problem: {problem}
        
        Verification approach:
        1. Solve the problem step by step
        2. Check each step for errors
        3. Verify the final answer using alternative methods
        4. Test edge cases if applicable
        5. Ensure the solution is reasonable and complete
        
        Show solution with thorough verification:
        """
    
    def _get_reasoning_type(self, path_index: int) -> str:
        """Get reasoning type based on path index."""
        types = ["analytical", "intuitive", "systematic", "creative", "verification"]
        return types[path_index % len(types)]
    
    def _extract_final_answer(self, response_text: str) -> str:
        """Extract the final answer from the response."""
        # Look for common answer patterns
        patterns = [
            "final answer:",
            "answer:",
            "solution:",
            "result:",
            "therefore:",
            "conclusion:"
        ]
        
        response_lower = response_text.lower()
        for pattern in patterns:
            if pattern in response_lower:
                # Find the position and extract text after it
                pos = response_lower.rfind(pattern)
                if pos != -1:
                    answer_part = response_text[pos + len(pattern):].strip()
                    # Take first line or sentence
                    answer = answer_part.split('\n')[0].split('.')[0].strip()
                    if answer:
                        return answer
        
        # Fallback: take last paragraph
        paragraphs = response_text.strip().split('\n\n')
        if paragraphs:
            return paragraphs[-1].strip()
        
        return response_text.strip()
    
    def _extract_reasoning_steps(self, response_text: str) -> List[str]:
        """Extract reasoning steps from the response."""
        steps = []
        
        # Split by numbered steps
        import re
        numbered_steps = re.split(r'\n\s*\d+\.', response_text)
        
        if len(numbered_steps) > 1:
            # Remove first element (before first number) and clean up
            for step in numbered_steps[1:]:
                clean_step = step.strip()
                if clean_step:
                    steps.append(clean_step)
        else:
            # Split by paragraphs as fallback
            paragraphs = response_text.split('\n\n')
            steps = [p.strip() for p in paragraphs if p.strip()]
        
        return steps
    
    async def _evaluate_path_quality(self, paths: List[Dict]) -> List[Dict]:
        """Evaluate the quality of reasoning paths."""
        for path in paths:
            # Basic quality metrics
            response_length = len(path["response"])
            step_count = len(path["reasoning_steps"])
            has_final_answer = bool(path["final_answer"])
            
            # Simple scoring (can be enhanced with Gemini evaluation)
            quality_score = 0.0
            
            # Length component (not too short, not too long)
            if 100 <= response_length <= 2000:
                quality_score += 0.3
            elif response_length > 50:
                quality_score += 0.15
            
            # Step count component
            if 3 <= step_count <= 10:
                quality_score += 0.3
            elif step_count >= 2:
                quality_score += 0.15
            
            # Final answer component
            if has_final_answer:
                quality_score += 0.2
            
            # Reasoning type bonus
            if path["reasoning_type"] in ["analytical", "systematic"]:
                quality_score += 0.1
            
            # Structure bonus (if contains structured elements)
            if any(keyword in path["response"].lower() for keyword in 
                   ["step", "first", "second", "therefore", "because", "since"]):
                quality_score += 0.1
            
            path["quality_score"] = min(1.0, quality_score)
        
        return paths
    
    async def select_best_paths(self, paths: List[Dict], top_k: int = 3) -> List[Dict]:
        """Select the best reasoning paths based on quality scores."""
        # Filter paths above threshold
        quality_paths = [p for p in paths if p["quality_score"] >= self.evaluation_threshold]
        
        # If not enough quality paths, include top-scoring ones
        if len(quality_paths) < top_k:
            quality_paths = sorted(paths, key=lambda x: x["quality_score"], reverse=True)
        
        return quality_paths[:top_k]
    
    def save_reasoning_paths(self, paths: List[Dict], problem: str, filepath: str):
        """Save reasoning paths to file for analysis."""
        data = {
            "problem": problem,
            "timestamp": datetime.now().isoformat(),
            "total_paths": len(paths),
            "paths": paths,
            "summary": {
                "avg_quality_score": sum(p["quality_score"] for p in paths) / len(paths) if paths else 0,
                "reasoning_types": [p["reasoning_type"] for p in paths],
                "top_path": paths[0] if paths else None
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2) 