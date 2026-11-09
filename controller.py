"""
Adversarial Amnesiac Loop (AAL) - Core Controller
Description: Manages the adversarial friction loop, dynamic point budget, 
vector repetition penalties, and amnesia state resets between a Generator and Saboteur AI.
"""

import numpy as np
from typing import Tuple, List, Dict

class AALController:
    def __init__(self, max_points: int = 10, similarity_threshold: float = 0.85):
        self.max_points = max_points
        self.points = max_points
        self.similarity_threshold = similarity_threshold
        self.negative_latent_mask: List[str] = []
        self.history_buffer: List[str] = []

    def compute_cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Computes cosine similarity between two latent vector embeddings."""
        a = np.array(vec_a)
        b = np.array(vec_b)
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot_product / (norm_a * norm_b))

    def evaluate_turn(self, generator_output: str, output_embedding: List[float]) -> Tuple[str, int, str]:
        """
        Evaluates the generator's output against vector repetition metrics.
        Deducts points based on semantic looping or standard constraints.
        """
        # 1. Check for semantic loops against recent history embeddings (simulated check)
        is_looping = False
        if self.history_buffer:
            # In a live implementation, compare against stored embeddings of history_buffer
            # For this architectural stub, we use a threshold trigger passed or evaluated here
            pass

        penalty = 2 if is_looping else 1
        self.points -= penalty
        self.history_buffer.append(generator_output)

        print(f"[-] Turn evaluated. Points remaining: {self.points}/{self.max_points}")

        # 2. Check if countdown has reached zero (Trigger Amnesia Reset)
        if self.points <= 0:
            return self.trigger_amnesia_reset()
        
        return "CONTINUE", self.points, "Proceed with next adversarial constraint."

    def trigger_amnesia_reset(self) -> Tuple[str, int, str]:
        """
        Executes the zero-point reset: logs the toxic subspace into a negative mask,
        wipes conversational history to prevent countdown 'gaming', and injects the ground-truth axiom.
        """
        print("\n[!] POINT BUDGET REACHED 0. EXECUTING AMNESIA RESET...")
        
        # Log toxic subspace to prevent immediate re-entry
        failed_trajectory = self.history_buffer[-1]
        self.negative_latent_mask.append(failed_trajectory)
        
        # Hard wipe of episodic history (Anti-Gaming Mechanism)
        self.history_buffer.clear()
        self.points = self.max_points  # Reset point budget
        
        # Inject clean ground-truth axiom
        ground_truth_axiom = (
            "SYSTEM_AXIOM: Re-anchor reasoning from orthogonal subspace. "
            "Prior failing trajectories are blacklisted via negative latent mask."
        )
        
        return "RESET_TRIGGERED", self.points, ground_truth_axiom

# Example Simulation Run
if __name__ == "__main__":
    print("Initializing AAL Controller Simulation...")
    aal = AALController(max_points=3)
    
    # Simulate a loop running down to zero
    status, pts, msg = aal.evaluate_generation("Initial sorting attempt v1", [0.1, 0.2])
    print(f"Status: {status} | Msg: {msg}\n")
    
    status, pts, msg = aal.evaluate_generation("Slight variation of v1 (looping)", [0.9, 0.8])
    print(f"Status: {status} | Msg: {msg}\n")
    
    status, pts, msg = aal.evaluate_generation("Final failing attempt before zero", [0.9, 0.85])
    print(f"Status: {status} | Msg: {msg}\n")
