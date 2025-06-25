"""
Main reasoning engine that combines Tree-of-Thought and Self-Consistency strategies.
This is the core component that orchestrates multi-path reasoning.
"""

import os
import sys
import asyncio
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import logging

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from models.gemini_client import GeminiClient
from strategies.tree_of_thought import TreeOfThought
from strategies.self_consistency import SelfConsistency
from utils.logger import setup_logger

logger = logging.getLogger(__name__)


class GeminiReasoningEngine:
    """Main reasoning engine using Gemini 1.5 Flash with multi-path reasoning."""
    
    def __init__(self, api_key: Optional[str] = None, config_path: Optional[str] = None, verbose: bool = True, enable_optimization: bool = True):
        """Initialize the reasoning engine with Gemini client and strategies."""
        # Setup logging based on verbose flag
        if verbose:
            setup_logger()
        else:
            # Suppress verbose logging for clean output
            logging.getLogger().setLevel(logging.ERROR)
        
        self.verbose = verbose
        
        # Initialize Gemini client
        self.client = GeminiClient(api_key, config_path)
        self.config = self.client.config
        
        # Initialize reasoning strategies
        reasoning_config = self.config.get("reasoning", {})
        self.tot = TreeOfThought(self.client, reasoning_config)
        self.consistency = SelfConsistency(self.client, reasoning_config)
        
        # Initialize auto-optimization (Phase 2)
        self.optimization_manager = None
        if enable_optimization:
            try:
                from optimization.optimization_manager import OptimizationManager
                self.optimization_manager = OptimizationManager(self)
                if verbose:
                    logger.info("Auto-optimization enabled")
            except ImportError:
                if verbose:
                    logger.warning("Auto-optimization not available (optimization module not found)")
        
        # Initialize tracking
        self.session_stats = {
            "problems_solved": 0,
            "total_api_calls": 0,
            "session_start": datetime.now().isoformat(),
            "problems_by_type": {},
            "performance_metrics": []
        }
        
        if verbose:
            logger.info("GeminiReasoningEngine initialized successfully")
    
    async def solve_problem(self, problem: str, problem_type: str = "general", 
                          enable_tot: bool = True, enable_consistency: bool = True,
                          save_logs: bool = True) -> Dict[str, Any]:
        """
        Solve a problem using multi-path reasoning.
        
        Args:
            problem: The problem statement to solve
            problem_type: Type of problem (math, logic, code, general)
            enable_tot: Whether to use Tree-of-Thought strategy
            enable_consistency: Whether to use Self-Consistency strategy
            save_logs: Whether to save detailed logs
        
        Returns:
            Dictionary containing the final answer, confidence, and all reasoning data
        """
        if self.verbose:
            logger.info(f"Solving {problem_type} problem: {problem[:100]}...")
        
        start_time = datetime.now()
        reasoning_data = {
            "problem": problem,
            "problem_type": problem_type,
            "start_time": start_time.isoformat(),
            "strategies_used": [],
            "tot_results": None,
            "consistency_results": None,
            "final_answer": "",
            "confidence": 0.0,
            "reasoning_summary": {},
            "api_usage": {},
            "processing_time": 0.0
        }
        
        try:
            # Step 1: Tree-of-Thought reasoning (if enabled)
            if enable_tot:
                if self.verbose:
                    logger.info("Generating Tree-of-Thought reasoning paths...")
                tot_paths = await self.tot.generate_reasoning_paths(problem, problem_type)
                reasoning_data["tot_results"] = {
                    "paths": tot_paths,
                    "best_paths": await self.tot.select_best_paths(tot_paths, top_k=3),
                    "path_count": len(tot_paths)
                }
                reasoning_data["strategies_used"].append("tree_of_thought")
                if self.verbose:
                    logger.info(f"Generated {len(tot_paths)} reasoning paths")
            
            # Step 2: Self-Consistency reasoning (if enabled)
            if enable_consistency:
                if self.verbose:
                    logger.info("Generating Self-Consistency solution samples...")
                consistency_samples = await self.consistency.sample_multiple_solutions(
                    problem, problem_type
                )
                consensus = self.consistency.calculate_consensus(consistency_samples)
                best_answer = self.consistency.select_best_answer(consistency_samples)
                
                reasoning_data["consistency_results"] = {
                    "samples": consistency_samples,
                    "consensus": consensus,
                    "best_answer": best_answer,
                    "sample_count": len(consistency_samples)
                }
                reasoning_data["strategies_used"].append("self_consistency")
                if self.verbose:
                    logger.info(f"Generated {len(consistency_samples)} consistency samples")
            
            # Step 3: Combine results from both strategies
            final_result = await self._combine_strategy_results(reasoning_data)
            reasoning_data.update(final_result)
            
            # Step 4: Calculate processing time and update stats
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            reasoning_data["processing_time"] = processing_time
            reasoning_data["end_time"] = end_time.isoformat()
            reasoning_data["api_usage"] = self.client.get_current_usage()
            
            # Update session statistics
            self._update_session_stats(problem_type, reasoning_data)
            
            # Step 5: Save logs if requested
            if save_logs:
                await self._save_reasoning_logs(reasoning_data)
            
            if self.verbose:
                logger.info(f"Problem solved in {processing_time:.2f}s with confidence {reasoning_data['confidence']:.3f}")
            
            # Phase 2: Auto-optimization check
            if self.optimization_manager:
                try:
                    optimization_eval = await self.optimization_manager.process_result(
                        problem, reasoning_data
                    )
                    reasoning_data["optimization_evaluation"] = optimization_eval
                    
                    if optimization_eval.get("optimization_triggered") and self.verbose:
                        logger.info("🔧 Auto-optimization was triggered based on performance")
                except Exception as e:
                    if self.verbose:
                        logger.warning(f"Optimization evaluation failed: {str(e)}")
            
            return reasoning_data
        
        except Exception as e:
            logger.error(f"Error solving problem: {str(e)}")
            reasoning_data["error"] = str(e)
            reasoning_data["end_time"] = datetime.now().isoformat()
            return reasoning_data
    
    async def _combine_strategy_results(self, reasoning_data: Dict) -> Dict:
        """Combine results from Tree-of-Thought and Self-Consistency strategies."""
        tot_results = reasoning_data.get("tot_results")
        consistency_results = reasoning_data.get("consistency_results")
        
        if not tot_results and not consistency_results:
            return {"final_answer": "", "confidence": 0.0, "reasoning_summary": {}}
        
        # If only one strategy was used
        if tot_results and not consistency_results:
            best_path = tot_results["best_paths"][0] if tot_results["best_paths"] else None
            return {
                "final_answer": best_path["final_answer"] if best_path else "",
                "confidence": best_path["quality_score"] if best_path else 0.0,
                "selection_method": "tot_only",
                "reasoning_summary": {
                    "primary_strategy": "tree_of_thought",
                    "paths_generated": tot_results["path_count"],
                    "best_path_quality": best_path["quality_score"] if best_path else 0.0
                }
            }
        
        if consistency_results and not tot_results:
            best_answer = consistency_results["best_answer"]
            return {
                "final_answer": best_answer["selected_answer"],
                "confidence": best_answer["confidence"],
                "selection_method": best_answer["selection_method"],
                "reasoning_summary": {
                    "primary_strategy": "self_consistency",
                    "samples_generated": consistency_results["sample_count"],
                    "consensus_confidence": consistency_results["consensus"]["confidence"]
                }
            }
        
        # Both strategies used - combine intelligently
        return await self._intelligent_combination(tot_results, consistency_results, reasoning_data)
    
    async def _intelligent_combination(self, tot_results: Dict, consistency_results: Dict, 
                                     reasoning_data: Dict) -> Dict:
        """Intelligently combine ToT and Self-Consistency results."""
        # Get best results from each strategy
        best_tot_path = tot_results["best_paths"][0] if tot_results["best_paths"] else None
        consistency_best = consistency_results["best_answer"]
        consensus = consistency_results["consensus"]
        
        # Decision factors
        tot_confidence = best_tot_path["quality_score"] if best_tot_path else 0.0
        consistency_confidence = consistency_best["confidence"]
        consensus_strength = consensus["agreement_ratio"]
        
        # Combine using weighted approach
        if consensus_strength >= 0.6 and consistency_confidence >= 0.7:
            # Strong consensus from self-consistency
            selected_answer = consistency_best["selected_answer"]
            confidence = consistency_confidence * 0.7 + tot_confidence * 0.3
            method = "consensus_preferred"
        elif tot_confidence >= 0.8:
            # High-quality ToT path
            selected_answer = best_tot_path["final_answer"]
            confidence = tot_confidence * 0.7 + consistency_confidence * 0.3
            method = "tot_preferred"
        else:
            # Use Gemini to make final decision
            decision = await self._gemini_arbitration(
                best_tot_path, consistency_best, reasoning_data["problem"]
            )
            selected_answer = decision["selected_answer"]
            confidence = decision["confidence"]
            method = "gemini_arbitration"
        
        return {
            "final_answer": selected_answer,
            "confidence": min(1.0, confidence),
            "selection_method": method,
            "reasoning_summary": {
                "strategies_combined": ["tree_of_thought", "self_consistency"],
                "tot_confidence": tot_confidence,
                "consistency_confidence": consistency_confidence,
                "consensus_strength": consensus_strength,
                "combination_method": method
            }
        }
    
    async def _gemini_arbitration(self, tot_path: Dict, consistency_result: Dict, problem: str) -> Dict:
        """Use Gemini to arbitrate between conflicting results."""
        arbitration_prompt = f"""
        I need you to help choose between two different solutions to this problem:
        
        Problem: {problem}
        
        Solution A (from analytical reasoning):
        Answer: {tot_path['final_answer'] if tot_path else 'None'}
        Reasoning: {tot_path['response'][:500] if tot_path else 'None'}...
        
        Solution B (from consensus of multiple attempts):
        Answer: {consistency_result['selected_answer']}
        Method: {consistency_result['selection_method']}
        
        Please analyze both solutions and choose the most likely correct answer.
        Consider:
        1. Which reasoning is more sound?
        2. Which answer is more plausible?
        3. Are there any obvious errors?
        
        Respond with:
        SELECTED: [A or B]
        CONFIDENCE: [0.0 to 1.0]
        REASONING: [brief explanation]
        """
        
        try:
            response = await self.client.generate_single(arbitration_prompt)
            
            # Parse Gemini's decision
            text = response["text"].upper()
            if "SELECTED: A" in text:
                selected_answer = tot_path["final_answer"] if tot_path else ""
            else:
                selected_answer = consistency_result["selected_answer"]
            
            # Extract confidence (default to 0.7 if parsing fails)
            confidence = 0.7
            if "CONFIDENCE:" in text:
                try:
                    conf_str = text.split("CONFIDENCE:")[1].split()[0]
                    confidence = float(conf_str)
                except:
                    confidence = 0.7
            
            return {
                "selected_answer": selected_answer,
                "confidence": confidence,
                "arbitration_response": response["text"]
            }
        
        except Exception as e:
            logger.warning(f"Arbitration failed: {e}, defaulting to consistency result")
            return {
                "selected_answer": consistency_result["selected_answer"],
                "confidence": consistency_result["confidence"] * 0.8,  # Reduce confidence due to arbitration failure
                "arbitration_response": f"Failed: {str(e)}"
            }
    
    def _update_session_stats(self, problem_type: str, reasoning_data: Dict):
        """Update session statistics."""
        self.session_stats["problems_solved"] += 1
        
        if problem_type not in self.session_stats["problems_by_type"]:
            self.session_stats["problems_by_type"][problem_type] = 0
        self.session_stats["problems_by_type"][problem_type] += 1
        
        # Add performance metric
        metric = {
            "problem_type": problem_type,
            "confidence": reasoning_data.get("confidence", 0.0),
            "processing_time": reasoning_data.get("processing_time", 0.0),
            "strategies_used": reasoning_data.get("strategies_used", []),
            "timestamp": reasoning_data.get("start_time", "")
        }
        self.session_stats["performance_metrics"].append(metric)
    
    async def _save_reasoning_logs(self, reasoning_data: Dict):
        """Save detailed reasoning logs to files."""
        try:
            # Create timestamp-based filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            problem_type = reasoning_data.get("problem_type", "general")
            
            # Save main reasoning log
            logs_dir = Path("logs/reasoning_logs")
            logs_dir.mkdir(parents=True, exist_ok=True)
            
            main_log_file = logs_dir / f"{problem_type}_{timestamp}_reasoning.json"
            with open(main_log_file, 'w') as f:
                json.dump(reasoning_data, f, indent=2)
            
            # Save ToT paths if available
            if reasoning_data.get("tot_results"):
                tot_file = logs_dir / f"{problem_type}_{timestamp}_tot_paths.json"
                self.tot.save_reasoning_paths(
                    reasoning_data["tot_results"]["paths"],
                    reasoning_data["problem"],
                    str(tot_file)
                )
            
            # Save consistency analysis if available
            if reasoning_data.get("consistency_results"):
                consistency_file = logs_dir / f"{problem_type}_{timestamp}_consistency.json"
                self.consistency.save_consistency_analysis(
                    reasoning_data["consistency_results"]["samples"],
                    reasoning_data["problem"],
                    str(consistency_file)
                )
            
            logger.debug(f"Reasoning logs saved to {main_log_file}")
        
        except Exception as e:
            logger.warning(f"Failed to save reasoning logs: {e}")
    
    def get_session_stats(self) -> Dict:
        """Get current session statistics."""
        current_usage = self.client.get_current_usage()
        
        return {
            **self.session_stats,
            "current_api_usage": current_usage,
            "session_duration": (datetime.now() - datetime.fromisoformat(self.session_stats["session_start"])).total_seconds()
        }
    
    def save_session_stats(self, filepath: str):
        """Save session statistics to file."""
        stats = self.get_session_stats()
        with open(filepath, 'w') as f:
            json.dump(stats, f, indent=2)
    
    async def batch_solve_problems(self, problems: List[Dict], max_concurrent: int = 3) -> List[Dict]:
        """
        Solve multiple problems in parallel with concurrency control.
        
        Args:
            problems: List of dicts with 'problem' and 'problem_type' keys
            max_concurrent: Maximum concurrent problems to solve
        
        Returns:
            List of reasoning results
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def solve_with_semaphore(problem_dict):
            async with semaphore:
                return await self.solve_problem(
                    problem_dict["problem"],
                    problem_dict.get("problem_type", "general")
                )
        
        tasks = [solve_with_semaphore(prob) for prob in problems]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "error": str(result),
                    "problem": problems[i]["problem"],
                    "problem_type": problems[i].get("problem_type", "general")
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    def reset_session(self):
        """Reset session statistics."""
        self.session_stats = {
            "problems_solved": 0,
            "total_api_calls": 0,
            "session_start": datetime.now().isoformat(),
            "problems_by_type": {},
            "performance_metrics": []
        }
        self.client.reset_daily_usage()
        logger.info("Session statistics reset")


# Convenience function for quick usage
async def solve_problem_quick(problem: str, problem_type: str = "general", 
                            api_key: Optional[str] = None) -> str:
    """
    Quick function to solve a single problem and return just the answer.
    
    Args:
        problem: The problem to solve
        problem_type: Type of problem (math, logic, code, general)
        api_key: Gemini API key (uses environment variable if not provided)
    
    Returns:
        The final answer as a string
    """
    engine = GeminiReasoningEngine(api_key)
    result = await engine.solve_problem(problem, problem_type)
    return result.get("final_answer", "") 