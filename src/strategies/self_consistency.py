"""
Self-Consistency strategy implementation for multi-sample reasoning.
Generates multiple solutions and uses majority voting for final answers.
"""

from typing import List, Dict, Optional
import asyncio
import json
import re
from datetime import datetime
from collections import Counter
import logging

logger = logging.getLogger(__name__)


class SelfConsistency:
    """Self-Consistency reasoning strategy using Gemini 1.5 Flash."""
    
    def __init__(self, gemini_client, config: Optional[Dict] = None):
        """Initialize Self-Consistency with Gemini client and configuration."""
        self.client = gemini_client
        self.config = config or {}
        self.num_samples = self.config.get("max_consistency_samples", 5)
        self.confidence_threshold = self.config.get("confidence_threshold", 0.7)
    
    async def sample_multiple_solutions(self, problem: str, problem_type: str = "general", 
                                      num_samples: Optional[int] = None) -> List[Dict]:
        """Generate multiple solution attempts for the same problem."""
        num_samples = num_samples or self.num_samples
        logger.info(f"Generating {num_samples} solution samples for consistency check")
        
        # Create base prompt for the problem type
        base_prompt = self._create_base_prompt(problem, problem_type)
        
        # Generate multiple solutions with variations
        solutions = await self.client.generate_with_variations(base_prompt, num_samples)
        
        # Process solutions
        processed_solutions = []
        for i, solution in enumerate(solutions):
            if "error" not in solution:
                processed_solution = {
                    "sample_id": i,
                    "prompt": solution["prompt"],
                    "response": solution["text"],
                    "timestamp": solution["timestamp"],
                    "final_answer": self._extract_final_answer(solution["text"]),
                    "normalized_answer": "",  # Will be populated
                    "reasoning_quality": 0.0,  # Will be calculated
                    "confidence_indicators": self._extract_confidence_indicators(solution["text"])
                }
                processed_solutions.append(processed_solution)
            else:
                logger.warning(f"Error in sample {i}: {solution['error']}")
        
        # Normalize answers for comparison
        processed_solutions = self._normalize_answers(processed_solutions, problem_type)
        
        # Calculate reasoning quality scores
        processed_solutions = self._evaluate_reasoning_quality(processed_solutions)
        
        logger.info(f"Generated {len(processed_solutions)} valid solution samples")
        return processed_solutions
    
    def _create_base_prompt(self, problem: str, problem_type: str) -> str:
        """Create base prompt for the problem type."""
        templates = {
            "math": f"""
            Solve this mathematical problem step by step:
            
            Problem: {problem}
            
            Instructions:
            1. Read the problem carefully
            2. Identify what information is given and what needs to be found
            3. Show all calculations clearly
            4. State your final answer clearly
            
            Solution:
            """,
            
            "logic": f"""
            Solve this logical reasoning problem:
            
            Problem: {problem}
            
            Instructions:
            1. Identify the logical structure
            2. Apply appropriate reasoning principles
            3. Show your step-by-step logic
            4. State your conclusion clearly
            
            Solution:
            """,
            
            "code": f"""
            Analyze and solve this code-related problem:
            
            Problem: {problem}
            
            Instructions:
            1. Understand the code or programming concept
            2. Identify the issue or requirement
            3. Provide a clear solution or explanation
            4. State your final answer
            
            Solution:
            """,
            
            "general": f"""
            Solve this problem step by step:
            
            Problem: {problem}
            
            Instructions:
            1. Understand what the problem is asking
            2. Break it down into manageable parts
            3. Work through the solution logically
            4. Provide a clear final answer
            
            Solution:
            """
        }
        
        return templates.get(problem_type, templates["general"])
    
    def _extract_final_answer(self, response_text: str) -> str:
        """Extract the final answer from response text."""
        if not response_text:
            return ""
        
        response_text = response_text.strip()
        
        # Look for "The answer is X" patterns
        patterns = [
            r"(?:the\s+)?(?:sum|answer|result)\s+(?:of\s+.+?\s+)?is\s+(.+?)\.",
            r"=\s*(.+?)\.",
            r"(\d+(?:\.\d+)?)\s*$"
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, response_text, re.IGNORECASE)
            if matches:
                answer = matches[-1].strip()
                if len(answer) > 0:
                    return answer
        
        # Fallback: last line with numbers
        lines = response_text.split("\n")
        for line in reversed(lines):
            line = line.strip()
            if re.search(r"\d+", line) and len(line) < 50:
                return line
        
        return response_text[:50].strip()
    def _extract_confidence_indicators(self, response_text: str) -> Dict:
        """Extract confidence indicators from the response."""
        indicators = {
            "certainty_words": 0,
            "uncertainty_words": 0,
            "hedge_words": 0,
            "verification_statements": 0
        }
        
        text_lower = response_text.lower()
        
        # Certainty indicators
        certainty_words = ["definitely", "certainly", "clearly", "obviously", "sure", "confident"]
        indicators["certainty_words"] = sum(1 for word in certainty_words if word in text_lower)
        
        # Uncertainty indicators
        uncertainty_words = ["might", "maybe", "possibly", "perhaps", "could be", "uncertain"]
        indicators["uncertainty_words"] = sum(1 for word in uncertainty_words if word in text_lower)
        
        # Hedge words
        hedge_words = ["approximately", "roughly", "about", "around", "seems", "appears"]
        indicators["hedge_words"] = sum(1 for word in hedge_words if word in text_lower)
        
        # Verification statements
        verification_phrases = ["let me check", "to verify", "double-check", "confirm", "validate"]
        indicators["verification_statements"] = sum(1 for phrase in verification_phrases if phrase in text_lower)
        
        return indicators
    
    def _normalize_answers(self, solutions: List[Dict], problem_type: str) -> List[Dict]:
        """Normalize answers for comparison."""
        for solution in solutions:
            answer = solution["final_answer"]
            normalized = self._normalize_single_answer(answer, problem_type)
            solution["normalized_answer"] = normalized
        
        return solutions
    
    def _normalize_single_answer(self, answer: str, problem_type: str) -> str:
        """Normalize a single answer for comparison."""
        if not answer:
            return ""
        
        answer = answer.strip().lower()
        
        if problem_type == "math":
            # Extract numbers and basic math expressions
            # Remove common words and focus on numerical content
            answer = re.sub(r'\b(the|answer|is|equals?|=)\b', '', answer)
            answer = re.sub(r'[^\d\.\-\+\*/\(\)\s]', '', answer)
            answer = answer.strip()
            
            # Try to evaluate simple expressions
            try:
                # Simple numeric answer
                if re.match(r'^-?\d+\.?\d*$', answer):
                    return str(float(answer))
            except:
                pass
        
        elif problem_type == "logic":
            # Normalize logical answers
            if "true" in answer or "yes" in answer or "correct" in answer:
                return "true"
            elif "false" in answer or "no" in answer or "incorrect" in answer:
                return "false"
        
        # General normalization
        # Remove punctuation and extra spaces
        answer = re.sub(r'[^\w\s]', '', answer)
        answer = re.sub(r'\s+', ' ', answer).strip()
        
        return answer
    
    def _evaluate_reasoning_quality(self, solutions: List[Dict]) -> List[Dict]:
        """Evaluate the quality of reasoning in each solution."""
        for solution in solutions:
            quality_score = 0.0
            response = solution["response"]
            
            # Length factor (not too short, not too long)
            length = len(response)
            if 100 <= length <= 1500:
                quality_score += 0.2
            elif length >= 50:
                quality_score += 0.1
            
            # Structure indicators
            structure_indicators = ["step", "first", "second", "next", "then", "finally"]
            structure_count = sum(1 for indicator in structure_indicators if indicator in response.lower())
            quality_score += min(0.3, structure_count * 0.1)
            
            # Mathematical reasoning (if applicable)
            if any(char in response for char in "=+-*/"):
                quality_score += 0.1
            
            # Confidence indicators
            confidence = solution["confidence_indicators"]
            confidence_score = (confidence["certainty_words"] * 0.1 - 
                              confidence["uncertainty_words"] * 0.05 +
                              confidence["verification_statements"] * 0.1)
            quality_score += max(0, min(0.2, confidence_score))
            
            # Final answer clarity
            if solution["final_answer"] and len(solution["final_answer"]) > 0:
                quality_score += 0.2
            
            solution["reasoning_quality"] = min(1.0, quality_score)
        
        return solutions
    
    def calculate_consensus(self, solutions: List[Dict]) -> Dict:
        """Calculate consensus among solutions."""
        if not solutions:
            return {"consensus_answer": "", "confidence": 0.0, "agreement_ratio": 0.0}
        
        # Count normalized answers
        normalized_answers = [sol["normalized_answer"] for sol in solutions if sol["normalized_answer"]]
        
        if not normalized_answers:
            return {"consensus_answer": "", "confidence": 0.0, "agreement_ratio": 0.0}
        
        answer_counts = Counter(normalized_answers)
        most_common_answer, most_common_count = answer_counts.most_common(1)[0]
        
        # Calculate agreement ratio
        agreement_ratio = most_common_count / len(normalized_answers)
        
        # Calculate weighted confidence based on reasoning quality
        supporting_solutions = [sol for sol in solutions if sol["normalized_answer"] == most_common_answer]
        quality_weights = [sol["reasoning_quality"] for sol in supporting_solutions]
        weighted_confidence = sum(quality_weights) / len(supporting_solutions) if supporting_solutions else 0.0
        
        # Combine agreement ratio and quality for final confidence
        final_confidence = (agreement_ratio * 0.7) + (weighted_confidence * 0.3)
        
        return {
            "consensus_answer": most_common_answer,
            "confidence": final_confidence,
            "agreement_ratio": agreement_ratio,
            "total_solutions": len(solutions),
            "supporting_solutions": most_common_count,
            "answer_distribution": dict(answer_counts),
            "quality_weighted_confidence": weighted_confidence
        }
    
    def select_best_answer(self, solutions: List[Dict]) -> Dict:
        """Select the best answer using self-consistency and quality metrics."""
        consensus = self.calculate_consensus(solutions)
        
        # If consensus is strong enough, use it
        if consensus["confidence"] >= self.confidence_threshold:
            return {
                "selected_answer": consensus["consensus_answer"],
                "selection_method": "consensus",
                "confidence": consensus["confidence"],
                "consensus_data": consensus
            }
        
        # Otherwise, select the highest quality individual answer
        best_solution = max(solutions, key=lambda x: x["reasoning_quality"])
        
        return {
            "selected_answer": best_solution["final_answer"],
            "selection_method": "highest_quality",
            "confidence": best_solution["reasoning_quality"],
            "consensus_data": consensus,
            "best_solution": best_solution
        }
    
    def analyze_consistency(self, solutions: List[Dict]) -> Dict:
        """Analyze the consistency patterns in the solutions."""
        if not solutions:
            return {}
        
        consensus = self.calculate_consensus(solutions)
        
        analysis = {
            "total_samples": len(solutions),
            "unique_answers": len(set(sol["normalized_answer"] for sol in solutions if sol["normalized_answer"])),
            "consensus_strength": consensus["agreement_ratio"],
            "average_quality": sum(sol["reasoning_quality"] for sol in solutions) / len(solutions),
            "quality_variance": self._calculate_variance([sol["reasoning_quality"] for sol in solutions]),
            "confidence_distribution": self._analyze_confidence_distribution(solutions),
            "answer_clusters": self._cluster_answers(solutions)
        }
        
        return analysis
    
    def _calculate_variance(self, values: List[float]) -> float:
        """Calculate variance of a list of values."""
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        return sum((x - mean) ** 2 for x in values) / len(values)
    
    def _analyze_confidence_distribution(self, solutions: List[Dict]) -> Dict:
        """Analyze confidence indicators across solutions."""
        all_indicators = [sol["confidence_indicators"] for sol in solutions]
        
        return {
            "avg_certainty_words": sum(ind["certainty_words"] for ind in all_indicators) / len(all_indicators),
            "avg_uncertainty_words": sum(ind["uncertainty_words"] for ind in all_indicators) / len(all_indicators),
            "avg_hedge_words": sum(ind["hedge_words"] for ind in all_indicators) / len(all_indicators),
            "avg_verification_statements": sum(ind["verification_statements"] for ind in all_indicators) / len(all_indicators)
        }
    
    def _cluster_answers(self, solutions: List[Dict]) -> Dict:
        """Cluster similar answers together."""
        clusters = {}
        for solution in solutions:
            answer = solution["normalized_answer"]
            if answer not in clusters:
                clusters[answer] = []
            clusters[answer].append(solution)
        
        # Sort clusters by size
        sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
        
        return {
            "clusters": {answer: len(solutions) for answer, solutions in sorted_clusters},
            "largest_cluster_size": len(sorted_clusters[0][1]) if sorted_clusters else 0,
            "cluster_count": len(clusters)
        }
    
    def save_consistency_analysis(self, solutions: List[Dict], problem: str, filepath: str):
        """Save consistency analysis to file."""
        consensus = self.calculate_consensus(solutions)
        analysis = self.analyze_consistency(solutions)
        best_answer = self.select_best_answer(solutions)
        
        data = {
            "problem": problem,
            "timestamp": datetime.now().isoformat(),
            "solutions": solutions,
            "consensus": consensus,
            "analysis": analysis,
            "best_answer": best_answer,
            "summary": {
                "total_samples": len(solutions),
                "consensus_confidence": consensus["confidence"],
                "selected_answer": best_answer["selected_answer"],
                "selection_method": best_answer["selection_method"]
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2) 