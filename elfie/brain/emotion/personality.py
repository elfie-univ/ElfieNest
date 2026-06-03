"""Personality Modifier for Big Five personality model.

This module provides personality-based modifiers for emotion accumulation and decay,
implementing the Wave 2 Task 3 requirements.
"""

from typing import Dict, Optional


def calculate_personality_modifier(personality: Dict[str, float], emotion: str) -> float:
    """Calculate personality-based modifier for an emotion.
    
    Args:
        personality: Big Five personality traits (values 0-1)
        emotion: Emotion type to calculate modifier for
        
    Returns:
        Modifier value (typically 0.5-1.5 range)
    """
    modifier = 1.0
    
    # Neuroticism affects negative emotions (fear, anger, sadness)
    # High neuroticism = faster accumulation = higher modifier
    if emotion in ['fear', 'anger', 'sadness']:
        neuroticism = personality.get('neuroticism', 0.5)
        modifier *= (0.5 + neuroticism)  # 0.5-1.5
    
    # Agreeableness affects anger and attachment
    agreeableness = personality.get('agreeableness', 0.5)
    if emotion == 'anger':
        # High agreeableness = slower anger accumulation = lower modifier
        modifier *= (1.5 - agreeableness)  # 1.0-0.5
    elif emotion == 'attachment':
        # High agreeableness = faster attachment = higher modifier
        modifier *= (0.5 + agreeableness)  # 1.0-1.5
    
    # Extraversion affects happiness
    if emotion == 'happiness':
        extraversion = personality.get('extraversion', 0.5)
        modifier *= (0.5 + extraversion)  # 0.5-1.5
    
    return modifier


class PersonalityModifier:
    """Personality-based modifier for emotion accumulation and decay.
    
    Implements the Big Five personality model effects on emotions:
    - Neuroticism: High = faster negative emotion growth, slower decay
    - Agreeableness: High = slower anger, faster attachment
    - Extraversion: High = faster happiness growth
    """
    
    def __init__(self, personality: Optional[Dict[str, float]] = None):
        """Initialize PersonalityModifier with Big Five personality traits.
        
        Args:
            personality: Dict with Big Five traits (neuroticism, agreeableness,
                        extraversion, conscientiousness, openness). Values 0-1.
                        Defaults to 0.5 for all traits if not provided.
        """
        if personality is None:
            personality = {}
        
        self.personality = {
            'neuroticism': personality.get('neuroticism', 0.5),
            'agreeableness': personality.get('agreeableness', 0.5),
            'extraversion': personality.get('extraversion', 0.5),
            'conscientiousness': personality.get('conscientiousness', 0.5),
            'openness': personality.get('openness', 0.5),
        }
    
    def get_accumulate_modifier(self, emotion: str) -> float:
        """Get accumulation modifier for an emotion.
        
        High neuroticism = faster negative emotion accumulation (modifier > 1.0)
        High agreeableness = slower anger, faster attachment
        High extraversion = faster happiness
        
        Args:
            emotion: Emotion type
            
        Returns:
            Accumulation modifier (0.5-1.5 range typical)
        """
        return calculate_personality_modifier(self.personality, emotion)
    
    def get_decay_modifier(self, emotion: str) -> float:
        """Get decay modifier for an emotion.
        
        Inverse of accumulation: higher accumulation = lower decay
        
        Args:
            emotion: Emotion type
            
        Returns:
            Decay modifier (inverse of accumulation, 0.67-2.0 range typical)
        """
        accumulate = self.get_accumulate_modifier(emotion)
        if accumulate == 0:
            return 1.0
        return 1.0 / accumulate
