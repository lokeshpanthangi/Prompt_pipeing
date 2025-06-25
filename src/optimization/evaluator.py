"""
Evaluation framework for detecting failures and measuring performance.
Part of the automated prompt optimization system.
"""

import re
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)


class PerformanceEvaluator:
    """Evaluates system performance and detects when optimization is needed."""
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the evaluator with configuration."""
        self.config = config or {
            "confidence_threshold": 0.7,
            "min_samples_for_optimization": 5,
            "evaluation_window": 20
        }
        self.failure_log = []
        self.performance_history = []
    
    def evaluate_result(self, problem: str, result: Dict, ground_truth: Optional[str] = None) -> Dict:
        """Evaluate a single problem result and determine if optimization is needed."""
        evaluation = {
            "timestamp": datetime.now().isoformat(),
            "problem": problem[:100] + "..." if len(problem) > 100 else problem,
            "problem_type": result.get("problem_type", "unknown"),
            "confidence": result.get("confidence", 0.0),
            "final_answer": result.get("final_answer", ""),
            "needs_optimization": False,
            "failure_reasons": []
        }
        
        # Check confidence threshold
        if evaluation["confidence"] < self.config["confidence_threshold"]:
            evaluation["needs_optimization"] = True
            evaluation["failure_reasons"].append(f"Low confidence: {evaluation['confidence']:.2f}")
        
        # Check for obvious errors
        final_answer = result.get("final_answer", "").strip()
        if not final_answer or len(final_answer) < 3:
            evaluation["needs_optimization"] = True
            evaluation["failure_reasons"].append("Empty or too short answer")
        
        # Add to history
        self.performance_history.append(evaluation)
        if len(self.performance_history) > self.config["evaluation_window"]:
            self.performance_history = self.performance_history[-self.config["evaluation_window"]:]
        
        # Log failure if optimization needed
        if evaluation["needs_optimization"]:
            self.failure_log.append(evaluation)
            logger.warning(f"Performance issue detected: {evaluation['failure_reasons']}")
        
        return evaluation
    
    def should_trigger_optimization(self) -> bool:
        """Determine if optimization should be triggered."""
        return len(self.failure_log) >= self.config["min_samples_for_optimization"]
    
    def get_optimization_report(self) -> Dict:
        """Generate optimization report."""
        return {
            "total_failures": len(self.failure_log),
            "should_optimize": self.should_trigger_optimization(),
            "recent_failures": self.failure_log[-5:] if self.failure_log else []
        }
    
    def _default_config(self) -> Dict:
        """Default evaluation configuration."""
        return {
            "confidence_threshold": 0.7,  # Below this triggers optimization
            "accuracy_threshold": 0.8,    # Below this triggers optimization
            "min_samples_for_optimization": 5,  # Need this many failures before optimizing
            "evaluation_window": 20,      # Look at last N problems for trends
            "problem_types": {
                "math": {
                    "answer_patterns": [r"\b\d+\.?\d*\b", r"\$\d+", r"\d+%"],
                    "keywords": ["calculate", "compute", "solve", "find"]
                },
                "logic": {
                    "answer_patterns": [r"\b(true|false|yes|no)\b", r"\b\d+\b"],
                    "keywords": ["if", "then", "therefore", "conclude"]
                },
                "code": {
                    "answer_patterns": [r"def\s+\w+", r"class\s+\w+", r"error", r"bug"],
                    "keywords": ["function", "variable", "error", "debug"]
                }
            }
        }
    
    def _detect_errors(self, result: Dict) -> List[str]:
        """Detect obvious errors in the result."""
        errors = []
        
        # Check for empty or nonsensical answers
        final_answer = result.get("final_answer", "").strip()
        if not final_answer or len(final_answer) < 3:
            errors.append("Empty or too short answer")
        
        # Check for error indicators in the response
        error_keywords = ["error", "cannot", "unable", "don't know", "unclear", "invalid"]
        if any(keyword in final_answer.lower() for keyword in error_keywords):
            errors.append("Error keywords detected in answer")
        
        # Check for inconsistent approach results
        if "tot_results" in result and result["tot_results"]:
            paths = result["tot_results"].get("paths", [])
            if len(paths) == 0:
                errors.append("No Tree-of-Thought paths generated")
        
        if "consistency_results" in result and result["consistency_results"]:
            samples = result["consistency_results"].get("samples", [])
            if len(samples) == 0:
                errors.append("No Self-Consistency samples generated")
        
        return errors
    
    def _calculate_accuracy(self, answer: str, ground_truth: str, problem_type: str) -> float:
        """Calculate accuracy by comparing answer to ground truth."""
        if not answer or not ground_truth:
            return 0.0
        
        # Normalize both answers
        answer_norm = self._normalize_answer(answer, problem_type)
        truth_norm = self._normalize_answer(ground_truth, problem_type)
        
        # Exact match
        if answer_norm == truth_norm:
            return 1.0
        
        # Fuzzy matching for numbers
        if problem_type == "math":
            return self._compare_numeric_answers(answer_norm, truth_norm)
        
        # Fuzzy matching for logic
        if problem_type == "logic":
            return self._compare_logic_answers(answer_norm, truth_norm)
        
        # General fuzzy matching
        return self._fuzzy_match(answer_norm, truth_norm)
    
    def _normalize_answer(self, answer: str, problem_type: str) -> str:
        """Normalize answer for comparison."""
        # Basic cleanup
        answer = answer.lower().strip()
        answer = re.sub(r'[^\w\s\d\.]', '', answer)
        
        # Extract relevant parts based on problem type
        if problem_type == "math":
            # Extract numbers
            numbers = re.findall(r'\d+\.?\d*', answer)
            return numbers[0] if numbers else answer
        
        elif problem_type == "logic":
            # Extract boolean-like answers
            if any(word in answer for word in ["true", "yes", "correct"]):
                return "true"
            elif any(word in answer for word in ["false", "no", "incorrect"]):
                return "false"
            # Extract numbers for logic puzzles
            numbers = re.findall(r'\d+', answer)
            return numbers[0] if numbers else answer
        
        return answer
    
    def _compare_numeric_answers(self, answer: str, truth: str) -> float:
        """Compare numeric answers with tolerance."""
        try:
            ans_num = float(answer)
            truth_num = float(truth)
            
            # Check if exactly equal
            if ans_num == truth_num:
                return 1.0
            
            # Check relative error (within 5%)
            if truth_num != 0:
                rel_error = abs(ans_num - truth_num) / abs(truth_num)
                if rel_error <= 0.05:
                    return 0.9
                elif rel_error <= 0.1:
                    return 0.7
                elif rel_error <= 0.2:
                    return 0.5
            
            return 0.0
        except ValueError:
            return 0.0
    
    def _compare_logic_answers(self, answer: str, truth: str) -> float:
        """Compare logical answers."""
        if answer == truth:
            return 1.0
        
        # Check for equivalent boolean expressions
        bool_map = {"true": ["yes", "correct", "1"], "false": ["no", "incorrect", "0"]}
        for canonical, equivalents in bool_map.items():
            if truth == canonical and answer in equivalents:
                return 0.9
            if answer == canonical and truth in equivalents:
                return 0.9
        
        return 0.0
    
    def _fuzzy_match(self, answer: str, truth: str) -> float:
        """Basic fuzzy string matching."""
        if answer in truth or truth in answer:
            return 0.8
        
        # Calculate word overlap
        answer_words = set(answer.split())
        truth_words = set(truth.split())
        
        if not answer_words or not truth_words:
            return 0.0
        
        overlap = len(answer_words.intersection(truth_words))
        union = len(answer_words.union(truth_words))
        
        return overlap / union if union > 0 else 0.0
    
    def _analyze_approach_consistency(self, result: Dict) -> List[str]:
        """Analyze consistency between different approaches."""
        issues = []
        
        # Check ToT path consistency
        if "tot_results" in result and result["tot_results"]:
            paths = result["tot_results"].get("paths", [])
            if len(paths) > 1:
                answers = [path.get("final_answer", "") for path in paths]
                answers = [ans for ans in answers if ans.strip()]
                if len(set(answers)) == len(answers):  # All different answers
                    issues.append("Tree-of-Thought approaches gave completely different answers")
        
        # Check Self-Consistency sample consistency
        if "consistency_results" in result and result["consistency_results"]:
            samples = result["consistency_results"].get("samples", [])
            if len(samples) > 1:
                answers = [sample.get("answer", "") for sample in samples]
                answers = [ans for ans in answers if ans.strip()]
                if len(set(answers)) > len(answers) * 0.7:  # Most answers are different
                    issues.append("Self-Consistency samples show high disagreement")
        
        return issues
    
    def _is_recent(self, timestamp: str, hours: int = 24) -> bool:
        """Check if timestamp is within recent timeframe."""
        try:
            ts = datetime.fromisoformat(timestamp)
            age = (datetime.now() - ts).total_seconds() / 3600
            return age <= hours
        except:
            return False
    
    def _generate_recommendations(self, failure_reasons: Dict, problem_types: Dict) -> List[str]:
        """Generate specific optimization recommendations."""
        recommendations = []
        
        # Address specific failure patterns
        if "Low confidence" in str(failure_reasons):
            recommendations.append("Improve prompts to increase model confidence")
        
        if "Low accuracy" in str(failure_reasons):
            recommendations.append("Optimize prompts for better accuracy")
        
        if "Empty or too short answer" in failure_reasons:
            recommendations.append("Add prompts encouraging detailed responses")
        
        # Address problem-specific issues
        for ptype, count in problem_types.items():
            if count > 2:
                recommendations.append(f"Focus optimization on {ptype} problem prompts")
        
        if not recommendations:
            recommendations.append("General prompt optimization recommended")
        
        return recommendations
    
    def _calculate_trends(self) -> Dict:
        """Calculate performance trends over time."""
        if len(self.performance_history) < 5:
            return {"insufficient_data": True}
        
        recent = self.performance_history[-10:]  # Last 10 problems
        older = self.performance_history[-20:-10] if len(self.performance_history) >= 20 else []
        
        recent_avg_confidence = sum(p["confidence"] for p in recent) / len(recent)
        older_avg_confidence = sum(p["confidence"] for p in older) / len(older) if older else recent_avg_confidence
        
        return {
            "confidence_trend": "improving" if recent_avg_confidence > older_avg_confidence else "declining",
            "recent_avg_confidence": recent_avg_confidence,
            "older_avg_confidence": older_avg_confidence,
            "confidence_change": recent_avg_confidence - older_avg_confidence
        }
    
    def save_evaluation_data(self, filepath: str):
        """Save evaluation data to file."""
        data = {
            "config": self.config,
            "failure_log": self.failure_log,
            "performance_history": self.performance_history[-50:],  # Save last 50
            "saved_at": datetime.now().isoformat()
        }
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Evaluation data saved to {filepath}")
    
    def load_evaluation_data(self, filepath: str):
        """Load evaluation data from file."""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            self.failure_log = data.get("failure_log", [])
            self.performance_history = data.get("performance_history", [])
            
            logger.info(f"Evaluation data loaded from {filepath}")
        except FileNotFoundError:
            logger.info(f"No existing evaluation data found at {filepath}")
        except Exception as e:
            logger.error(f"Error loading evaluation data: {str(e)}") 