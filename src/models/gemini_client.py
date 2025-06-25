"""
Gemini 1.5 Flash client for the reasoning system.
Handles all interactions with Google's Gemini API.
"""

import google.generativeai as genai
from typing import List, Dict, Optional, Any
import asyncio
import time
import json
import os
from datetime import datetime, timedelta
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class GeminiClient:
    """Client for interacting with Gemini 1.5 Flash API."""
    
    def __init__(self, api_key: Optional[str] = None, config_path: Optional[str] = None):
        """Initialize Gemini client with API key and configuration."""
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be provided or set in environment")
        
        genai.configure(api_key=self.api_key)
        
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Initialize model
        self.model = genai.GenerativeModel(
            model_name=self.config["gemini"]["model_name"]
        )
        
        # Initialize usage tracking
        self.usage_stats = {
            "total_requests": 0,
            "total_tokens": 0,
            "daily_requests": 0,
            "daily_reset": datetime.now().date(),
            "cost_estimate": 0.0
        }
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 60 / self.config["cost_management"]["rate_limit_requests_per_minute"]
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load configuration from YAML file."""
        if config_path is None:
            config_path = str(Path(__file__).parent.parent.parent / "config" / "gemini_config.yaml")
        
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
    async def _rate_limit(self):
        """Implement rate limiting to respect API limits."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _update_usage_stats(self, response: Any):
        """Update usage statistics and cost tracking."""
        self.usage_stats["total_requests"] += 1
        
        # Reset daily counter if needed
        if datetime.now().date() > self.usage_stats["daily_reset"]:
            self.usage_stats["daily_requests"] = 0
            self.usage_stats["daily_reset"] = datetime.now().date()
        
        self.usage_stats["daily_requests"] += 1
        
        # Estimate tokens (Gemini Flash pricing is very low)
        # This is an approximation - actual usage tracking would need API response data
        estimated_tokens = len(response.text) // 4  # Rough estimate
        self.usage_stats["total_tokens"] += estimated_tokens
        
        # Gemini 1.5 Flash is approximately $0.075 per 1M input tokens, $0.30 per 1M output tokens
        self.usage_stats["cost_estimate"] += estimated_tokens * 0.0000003  # Conservative estimate
    
    async def generate_single(self, prompt: str, **kwargs) -> Dict:
        """Generate a single response from Gemini."""
        await self._rate_limit()
        
        # Check daily limits
        if self.usage_stats["daily_requests"] >= self.config["cost_management"]["max_daily_requests"]:
            raise Exception("Daily API request limit reached")
        
        try:
            # Merge generation config with any overrides
            generation_config = {**self.config["gemini"]["generation_config"], **kwargs}
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=generation_config
            )
            
            self._update_usage_stats(response)
            
            return {
                "text": response.text,
                "prompt": prompt,
                "timestamp": datetime.now().isoformat(),
                "model": self.config["gemini"]["model_name"],
                "generation_config": generation_config,
                "usage_stats": self.get_current_usage()
            }
        
        except Exception as e:
            return {
                "error": str(e),
                "prompt": prompt,
                "timestamp": datetime.now().isoformat(),
                "model": self.config["gemini"]["model_name"]
            }
    
    async def generate_multiple(self, prompts: List[str], **kwargs) -> List[Dict]:
        """Generate multiple responses in parallel with rate limiting."""
        tasks = []
        for prompt in prompts:
            task = self.generate_single(prompt, **kwargs)
            tasks.append(task)
            # Small delay between task creation to distribute load
            await asyncio.sleep(0.1)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "error": str(result),
                    "prompt": prompts[i],
                    "timestamp": datetime.now().isoformat()
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def generate_with_variations(self, base_prompt: str, num_variations: int = 5) -> List[Dict]:
        """Generate multiple responses with slight prompt variations for self-consistency."""
        variation_prompts = self._create_prompt_variations(base_prompt, num_variations)
        
        # Use slightly different temperatures for each variation
        results = []
        for i, prompt in enumerate(variation_prompts):
            temp_variation = self.config["gemini"]["generation_config"]["temperature"] + (i * 0.1 - 0.2)
            temp_variation = max(0.1, min(1.0, temp_variation))  # Clamp between 0.1 and 1.0
            
            result = await self.generate_single(prompt, temperature=temp_variation)
            results.append(result)
        
        return results
    
    def _create_prompt_variations(self, base_prompt: str, num_variations: int) -> List[str]:
        """Create slight variations of the base prompt for self-consistency."""
        variations = [base_prompt]  # Include original
        
        prefixes = [
            "Think step by step: ",
            "Solve this carefully: ",
            "Let's work through this: ",
            "Analyze this problem: ",
            "Consider this question: "
        ]
        
        suffixes = [
            "\n\nShow your reasoning clearly.",
            "\n\nExplain your approach.",
            "\n\nBreak this down step by step.",
            "\n\nProvide a detailed solution.",
            "\n\nWalk through your thinking."
        ]
        
        for i in range(1, num_variations):
            if i <= len(prefixes):
                variation = prefixes[i-1] + base_prompt
            else:
                variation = base_prompt + suffixes[(i-1) % len(suffixes)]
            variations.append(variation)
        
        return variations
    
    def get_current_usage(self) -> Dict:
        """Get current usage statistics."""
        return {
            "total_requests": self.usage_stats["total_requests"],
            "daily_requests": self.usage_stats["daily_requests"],
            "total_tokens": self.usage_stats["total_tokens"],
            "estimated_cost": round(self.usage_stats["cost_estimate"], 4),
            "daily_limit": self.config["cost_management"]["max_daily_requests"],
            "requests_remaining": self.config["cost_management"]["max_daily_requests"] - self.usage_stats["daily_requests"]
        }
    
    def save_usage_stats(self, filepath: str):
        """Save usage statistics to file."""
        stats = {
            **self.get_current_usage(),
            "last_updated": datetime.now().isoformat(),
            "daily_reset": self.usage_stats["daily_reset"].isoformat()
        }
        
        with open(filepath, 'w') as f:
            json.dump(stats, f, indent=2)
    
    def reset_daily_usage(self):
        """Reset daily usage counters (for testing or manual reset)."""
        self.usage_stats["daily_requests"] = 0
        self.usage_stats["daily_reset"] = datetime.now().date() 