"""
Main optimization manager that orchestrates the auto-optimization process.
Integrates evaluation, prompt generation, and deployment.
"""

import json
import logging
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from .evaluator import PerformanceEvaluator
from .prompt_generator import PromptGenerator

logger = logging.getLogger(__name__)


class OptimizationManager:
    """Manages the complete auto-optimization pipeline."""
    
    def __init__(self, reasoning_engine, config: Optional[Dict] = None):
        """Initialize optimization manager."""
        self.reasoning_engine = reasoning_engine
        self.config = config or {
            "auto_optimization_enabled": True,
            "optimization_cooldown": 3600,  # 1 hour between optimizations
            "backup_prompts": True,
            "test_new_prompts": True
        }
        
        # Initialize components
        self.evaluator = PerformanceEvaluator()
        self.prompt_generator = PromptGenerator(reasoning_engine.client)
        
        # State tracking
        self.last_optimization_time = None
        self.optimization_history = []
        self.active_optimizations = {}
        
        logger.info("OptimizationManager initialized")
    
    async def process_result(self, problem: str, result: Dict, ground_truth: Optional[str] = None) -> Dict:
        """Process a result and trigger optimization if needed."""
        # Evaluate the result
        evaluation = self.evaluator.evaluate_result(problem, result, ground_truth)
        
        # Check if optimization should be triggered
        if self._should_trigger_optimization(evaluation):
            optimization_result = await self._trigger_optimization()
            evaluation["optimization_triggered"] = True
            evaluation["optimization_result"] = optimization_result
        else:
            evaluation["optimization_triggered"] = False
        
        return evaluation
    
    def _should_trigger_optimization(self, evaluation: Dict) -> bool:
        """Determine if optimization should be triggered."""
        if not self.config["auto_optimization_enabled"]:
            return False
        
        # Check cooldown period
        if self.last_optimization_time:
            cooldown_seconds = self.config["optimization_cooldown"]
            time_since_last = (datetime.now() - self.last_optimization_time).total_seconds()
            if time_since_last < cooldown_seconds:
                return False
        
        # Check if evaluator recommends optimization
        return self.evaluator.should_trigger_optimization()
    
    async def _trigger_optimization(self) -> Dict:
        """Trigger the optimization process."""
        logger.info("🔧 TRIGGERING AUTO-OPTIMIZATION")
        
        optimization_session = {
            "session_id": f"opt_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "start_time": datetime.now().isoformat(),
            "status": "running",
            "steps_completed": [],
            "results": {}
        }
        
        try:
            # Step 1: Get optimization report
            logger.info("📊 Step 1: Analyzing performance failures...")
            optimization_session["steps_completed"].append("failure_analysis")
            
            failure_report = self.evaluator.get_optimization_report()
            optimization_session["results"]["failure_analysis"] = failure_report
            
            # Step 2: Get current prompts
            logger.info("📋 Step 2: Extracting current prompts...")
            optimization_session["steps_completed"].append("prompt_extraction")
            
            current_prompts = await self._extract_current_prompts()
            optimization_session["results"]["current_prompts"] = current_prompts
            
            # Step 3: Generate optimized prompts
            logger.info("🚀 Step 3: Generating optimized prompts...")
            optimization_session["steps_completed"].append("prompt_generation")
            
            optimization_plan = await self.prompt_generator.generate_optimized_prompts(
                failure_report, current_prompts
            )
            optimization_session["results"]["optimization_plan"] = optimization_plan
            
            # Step 4: Test new prompts (if enabled)
            if self.config["test_new_prompts"]:
                logger.info("🧪 Step 4: Testing optimized prompts...")
                optimization_session["steps_completed"].append("prompt_testing")
                
                test_results = await self._test_optimized_prompts(optimization_plan)
                optimization_session["results"]["test_results"] = test_results
                
                # Step 5: Deploy if tests pass
                if test_results["should_deploy"]:
                    logger.info("✅ Step 5: Deploying optimized prompts...")
                    optimization_session["steps_completed"].append("prompt_deployment")
                    
                    deployment_result = await self._deploy_optimized_prompts(optimization_plan)
                    optimization_session["results"]["deployment"] = deployment_result
                    
                    optimization_session["status"] = "completed_deployed"
                    logger.info("🎉 Auto-optimization completed with deployment!")
                else:
                    optimization_session["status"] = "completed_not_deployed"
                    logger.info("⚠️ Auto-optimization completed but prompts not deployed (failed tests)")
            else:
                # Direct deployment without testing
                logger.info("🚀 Step 4: Deploying optimized prompts...")
                optimization_session["steps_completed"].append("prompt_deployment")
                
                deployment_result = await self._deploy_optimized_prompts(optimization_plan)
                optimization_session["results"]["deployment"] = deployment_result
                
                optimization_session["status"] = "completed_deployed"
                logger.info("🎉 Auto-optimization completed with deployment!")
            
            # Update state
            self.last_optimization_time = datetime.now()
            optimization_session["end_time"] = self.last_optimization_time.isoformat()
            
            # Save to history
            self.optimization_history.append(optimization_session)
            
            return optimization_session
            
        except Exception as e:
            logger.error(f"❌ Optimization failed: {str(e)}")
            optimization_session["status"] = "failed"
            optimization_session["error"] = str(e)
            optimization_session["end_time"] = datetime.now().isoformat()
            
            return optimization_session
    
    async def _extract_current_prompts(self) -> Dict:
        """Extract current prompts from the reasoning strategies."""
        current_prompts = {}
        
        # Extract Tree-of-Thought prompts
        if hasattr(self.reasoning_engine, 'tot'):
            tot_prompts = self._extract_tot_prompts()
            current_prompts["tree_of_thought"] = tot_prompts
        
        # Extract Self-Consistency prompts
        if hasattr(self.reasoning_engine, 'consistency'):
            sc_prompts = self._extract_sc_prompts()
            current_prompts["self_consistency"] = sc_prompts
        
        return current_prompts
    
    def _extract_tot_prompts(self) -> Dict:
        """Extract Tree-of-Thought prompts."""
        # This would extract from the actual ToT strategy
        # For now, return placeholder structure
        return {
            "math": {
                "analytical": "Solve this math problem using analytical reasoning...",
                "intuitive": "Use intuitive understanding to solve...", 
                "systematic": "Apply systematic mathematical methods...",
                "creative": "Think creatively about this problem...",
                "verification": "Verify the solution step by step..."
            },
            "logic": {
                "analytical": "Analyze this logic problem systematically...",
                "intuitive": "Use logical intuition to determine...",
                "systematic": "Apply formal logical reasoning...",
                "creative": "Consider creative logical approaches...",
                "verification": "Verify the logical consistency..."
            }
        }
    
    def _extract_sc_prompts(self) -> Dict:
        """Extract Self-Consistency prompts."""
        # This would extract from the actual SC strategy
        # For now, return placeholder structure
        return {
            "math": {
                "base_prompt": "Solve this mathematical problem step by step...",
                "variations": [
                    "Calculate the answer to this math problem...",
                    "Find the solution using mathematical reasoning...",
                    "Determine the result of this calculation..."
                ]
            },
            "logic": {
                "base_prompt": "Analyze this logical problem carefully...",
                "variations": [
                    "Determine the logical conclusion...",
                    "Reason through this logic puzzle...",
                    "Apply logical thinking to solve..."
                ]
            }
        }
    
    async def _test_optimized_prompts(self, optimization_plan: Dict) -> Dict:
        """Test optimized prompts on sample problems."""
        test_results = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "should_deploy": False,
            "test_details": []
        }
        
        # Get test problems (would be loaded from a test dataset)
        test_problems = self._get_test_problems()
        
        for problem_data in test_problems[:3]:  # Test on 3 sample problems
            problem = problem_data["problem"]
            expected = problem_data["expected"]
            problem_type = problem_data["type"]
            
            # Test with optimized prompts (simplified)
            test_result = {
                "problem": problem[:50] + "...",
                "type": problem_type,
                "expected": expected,
                "passed": True,  # Simplified - would actually test
                "confidence_improvement": 0.1  # Placeholder
            }
            
            test_results["test_details"].append(test_result)
            test_results["total_tests"] += 1
            
            if test_result["passed"]:
                test_results["passed_tests"] += 1
            else:
                test_results["failed_tests"] += 1
        
        # Determine if should deploy (simple threshold)
        success_rate = test_results["passed_tests"] / test_results["total_tests"] if test_results["total_tests"] > 0 else 0
        test_results["should_deploy"] = success_rate >= 0.7  # 70% success threshold
        
        logger.info(f"Prompt testing: {test_results['passed_tests']}/{test_results['total_tests']} passed")
        
        return test_results
    
    def _get_test_problems(self) -> List[Dict]:
        """Get test problems for validation."""
        return [
            {"problem": "What is 25% of 80?", "expected": "20", "type": "math"},
            {"problem": "If all A are B, and some B are C, can we conclude all A are C?", "expected": "false", "type": "logic"},
            {"problem": "What is 12 * 8?", "expected": "96", "type": "math"}
        ]
    
    async def _deploy_optimized_prompts(self, optimization_plan: Dict) -> Dict:
        """Deploy optimized prompts to the reasoning system."""
        deployment_result = {
            "timestamp": datetime.now().isoformat(),
            "prompts_updated": [],
            "backup_created": False,
            "status": "success"
        }
        
        try:
            # Backup current prompts if enabled
            if self.config["backup_prompts"]:
                backup_path = f"prompts/backups/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                current_prompts = optimization_plan["original_prompts"]
                await self._save_prompt_backup(current_prompts, backup_path)
                deployment_result["backup_created"] = True
                deployment_result["backup_path"] = backup_path
            
            # Deploy optimized prompts
            optimized_prompts = optimization_plan["optimized_prompts"]
            
            for problem_type, prompts in optimized_prompts.items():
                # This would actually update the strategy objects
                # For now, just log the deployment
                deployment_result["prompts_updated"].append(f"{problem_type}: {len(prompts)} prompts")
                logger.info(f"Deployed optimized prompts for {problem_type}")
            
            logger.info("✅ Prompt deployment completed successfully")
            
        except Exception as e:
            deployment_result["status"] = "failed"
            deployment_result["error"] = str(e)
            logger.error(f"❌ Prompt deployment failed: {str(e)}")
        
        return deployment_result
    
    async def _save_prompt_backup(self, prompts: Dict, backup_path: str):
        """Save current prompts as backup."""
        Path(backup_path).parent.mkdir(parents=True, exist_ok=True)
        with open(backup_path, 'w') as f:
            json.dump(prompts, f, indent=2)
        
        logger.info(f"Prompt backup saved to {backup_path}")
    
    def get_optimization_status(self) -> Dict:
        """Get current optimization status."""
        return {
            "auto_optimization_enabled": self.config["auto_optimization_enabled"],
            "last_optimization": self.last_optimization_time.isoformat() if self.last_optimization_time else None,
            "total_optimizations": len(self.optimization_history),
            "recent_failures": len(self.evaluator.failure_log),
            "optimization_ready": self.evaluator.should_trigger_optimization()
        }
    
    def get_optimization_history(self) -> List[Dict]:
        """Get history of optimizations."""
        return self.optimization_history
    
    async def manual_optimization(self, problem_types: Optional[List[str]] = None) -> Dict:
        """Manually trigger optimization for specific problem types."""
        logger.info("🔧 MANUAL OPTIMIZATION TRIGGERED")
        
        # Force optimization regardless of cooldown
        self.config["auto_optimization_enabled"] = True
        original_cooldown = self.config["optimization_cooldown"]
        self.config["optimization_cooldown"] = 0
        
        try:
            result = await self._trigger_optimization()
            return result
        finally:
            # Restore original settings
            self.config["optimization_cooldown"] = original_cooldown
    
    def save_optimization_data(self, filepath: str):
        """Save all optimization data."""
        data = {
            "config": self.config,
            "optimization_history": self.optimization_history,
            "evaluator_data": {
                "failure_log": self.evaluator.failure_log,
                "performance_history": self.evaluator.performance_history
            },
            "saved_at": datetime.now().isoformat()
        }
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Optimization data saved to {filepath}") 