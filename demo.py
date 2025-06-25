#!/usr/bin/env python3
"""
Demo script for the Smart AI Reasoning System using Gemini 1.5 Flash.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to Python path
sys.path.append(str(Path(__file__).parent / "src"))

# Suppress verbose logging for clean output
logging.getLogger().setLevel(logging.ERROR)

from core.reasoning_engine import GeminiReasoningEngine


async def solve_dynamic_problem(problem: str, problem_type: str):
    """Solve a problem using multi-path reasoning with clean output."""
    print(f"\n🔍 SOLVING {problem_type.upper()} PROBLEM")
    print("=" * 60)
    print(f"❓ Question: {problem}")
    print("\n🧠 Thinking through multiple approaches...")
    
    # Initialize reasoning engine with clean output
    engine = GeminiReasoningEngine(verbose=False)
    
    # Solve the problem
    result = await engine.solve_problem(problem, problem_type=problem_type)
    
    # Display individual approach results with answers
    if 'tot_results' in result and result['tot_results'] and result['tot_results']['paths']:
        print(f"\n📋 TREE-OF-THOUGHT APPROACHES:")
        print("-" * 50)
        for i, path in enumerate(result['tot_results']['paths'][:3], 1):  # Show top 3 approaches
            approach_type = path.get('type', 'Unknown').title()
            # Extract the final answer from this approach
            final_answer = path.get('final_answer', 'No answer extracted')
            quality_score = path.get('quality_score', 0.0)
            
            print(f"  {i}. {approach_type} Approach:")
            print(f"     💡 Answer: {final_answer}")
            print(f"     📊 Quality: {quality_score:.2f}")
            if 'response' in path and path['response']:
                reasoning = path['response'][:120].replace('\n', ' ').strip()
                print(f"     🧠 Reasoning: {reasoning}...")
            print()
    
    if 'consistency_results' in result and result['consistency_results'] and result['consistency_results']['samples']:
        print(f"🔄 SELF-CONSISTENCY SAMPLES:")
        print("-" * 50)
        for i, sample in enumerate(result['consistency_results']['samples'][:3], 1):  # Show top 3
            # Extract answer from consistency sample
            sample_answer = sample.get('final_answer', 'No answer extracted')
            confidence = sample.get('reasoning_quality', 0.0)
            
            print(f"  {i}. Sample {i}:")
            print(f"     💡 Answer: {sample_answer}")
            print(f"     📊 Confidence: {confidence:.2f}")
            if 'response' in sample and sample['response']:
                reasoning = sample['response'][:100].replace('\n', ' ').strip()
                print(f"     🧠 Reasoning: {reasoning}...")
            print()
    
    # Display final results
    print(f"\n✅ FINAL ANSWER: {result['final_answer']}")
    print(f"🎯 CONFIDENCE: {result['confidence']:.1%}")
    print(f"⚡ TIME: {result.get('processing_time', 0):.1f}s")
    
    # Show optimization status (Phase 2)
    if 'optimization_evaluation' in result:
        opt_eval = result['optimization_evaluation']
        if opt_eval.get('optimization_triggered'):
            print(f"🔧 AUTO-OPTIMIZATION: ✅ Triggered (System is learning from this result)")
        elif opt_eval.get('needs_optimization'):
            print(f"🔧 AUTO-OPTIMIZATION: ⏳ Monitoring ({len(engine.optimization_manager.evaluator.failure_log) if engine.optimization_manager else 0} issues detected)")
        else:
            print(f"🔧 AUTO-OPTIMIZATION: ✅ Performance OK")
    
    return result


def get_user_input():
    """Get problem and type from user input."""
    print("\n" + "="*60)
    print("🤖 SMART AI REASONING SYSTEM")
    print("🧠 Multi-Path Problem Solver")
    print("="*60)
    
    print("\nSupported problem types:")
    print("  📊 math     - Mathematical calculations and word problems")
    print("  🧩 logic    - Logic puzzles and reasoning problems") 
    print("  🐛 code     - Code debugging and programming issues")
    print("  🌟 general - General questions and analysis")
    
    while True:
        problem = input("\n❓ Enter your problem/question: ").strip()
        if problem:
            break
        print("❌ Please enter a valid problem.")
    
    while True:
        problem_type = input("📝 Problem type (math/logic/code/general): ").strip().lower()
        if problem_type in ['math', 'logic', 'code', 'general']:
            break
        print("❌ Please enter a valid type: math, logic, code, or general")
    
    return problem, problem_type


def check_environment():
    """Check if environment is properly configured."""
    print("🔧 ENVIRONMENT CHECK")
    print("=" * 50)
    
    # Check for API key - first try environment, then .env file
    api_key = os.getenv("GEMINI_API_KEY")
    
    # If not found in environment, try to set it from .env manually
    if not api_key:
        try:
            with open('.env', 'r') as f:
                for line in f:
                    if line.startswith('GEMINI_API_KEY='):
                        api_key = line.split('=', 1)[1].strip()
                        os.environ['GEMINI_API_KEY'] = api_key
                        break
        except FileNotFoundError:
            pass
    
    if api_key:
        print("✅ GEMINI_API_KEY found in environment")
    else:
        print("❌ GEMINI_API_KEY not found!")
        print("Please set your Gemini API key:")
        print("export GEMINI_API_KEY='your_api_key_here'")
        print("Or create a .env file with: GEMINI_API_KEY=your_key_here")
        return False
    
    print("✅ Environment check passed!")
    return True


async def main():
    """Run the interactive reasoning system."""
    # Check environment first
    if not check_environment():
        print("\nPlease fix the environment issues before running the demo.")
        return
    
    # Show model info once at startup
    print(f"\n🤖 MODEL: Gemini 1.5 Flash")
    print(f"🔧 STATUS: Multi-Path Reasoning Active")
    
    while True:
        try:
            # Get user input
            problem, problem_type = get_user_input()
            
            # Solve the problem
            await solve_dynamic_problem(problem, problem_type)
            
            # Ask if user wants to continue
            print(f"\n{'='*60}")
            continue_choice = input("🔄 Solve another problem? (y/n): ").strip().lower()
            if continue_choice not in ['y', 'yes']:
                print("\n👋 Thank you for using the Smart AI Reasoning System!")
                break
                
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            print("Please try again with a different problem.")


if __name__ == "__main__":
    asyncio.run(main())