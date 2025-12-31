"""
Discord Webhook Manager for SantaMacro
Handles Discord notifications for various macro events
"""
import json
import time
import threading
from typing import Dict, Any, Optional
from datetime import datetime


class WebhookManager:
    """Manages Discord webhook notifications"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.webhook_config = config.get("webhooks", {})
        self.enabled = self.webhook_config.get("enabled", False)
        self.webhook_url = self.webhook_config.get("discord_url", "")
        self.events = self.webhook_config.get("events", {})
        
        # Rate limiting
        self.last_sent = {}
        self.rate_limit_seconds = 5  # Minimum 5 seconds between same event types
        
        # Session tracking
        self.session_start = time.time()
        self.stats = {
            "santa_detections": 0,
            "attacks_completed": 0,
            "total_runtime": 0
        }
    
    def update_config(self, config: Dict[str, Any]):
        """Update webhook configuration"""
        self.config = config
        self.webhook_config = config.get("webhooks", {})
        self.enabled = self.webhook_config.get("enabled", False)
        self.webhook_url = self.webhook_config.get("discord_url", "")
        self.events = self.webhook_config.get("events", {})
    
    def is_event_enabled(self, event_type: str) -> bool:
        """Check if an event type is enabled"""
        return self.enabled and self.events.get(event_type, False)
    
    def should_send(self, event_type: str) -> bool:
        """Check if we should send this event (rate limiting)"""
        if not self.is_event_enabled(event_type):
            return False
        
        now = time.time()
        last_sent = self.last_sent.get(event_type, 0)
        
        if now - last_sent < self.rate_limit_seconds:
            return False
        
        self.last_sent[event_type] = now
        return True
    
    def send_webhook(self, event_type: str, title: str, description: str, 
                    color: int = 0xdc3545, fields: Optional[list] = None):
        """Send a webhook message to Discord"""
        if not self.should_send(event_type):
            return
        
        if not self.webhook_url:
            return
        
        # Create embed
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "SantaMacro",
                "icon_url": "https://i.imgur.com/santa_icon.png"  # You can replace with actual icon
            }
        }
        
        if fields:
            embed["fields"] = fields
        
        # Add session info for some events
        if event_type in ["macro_started", "macro_stopped"]:
            runtime = time.time() - self.session_start
            embed["fields"] = embed.get("fields", []) + [
                {
                    "name": "Session Stats",
                    "value": f"Runtime: {runtime/60:.1f} minutes\nDetections: {self.stats['santa_detections']}\nAttacks: {self.stats['attacks_completed']}",
                    "inline": True
                }
            ]
        
        payload = {
            "embeds": [embed]
        }
        
        # Send in background thread to avoid blocking
        thread = threading.Thread(target=self._send_request, args=(payload,))
        thread.daemon = True
        thread.start()
    
    def _send_request(self, payload: Dict[str, Any]):
        """Send the actual HTTP request"""
        try:
            import requests
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 204:
                print(f"Webhook failed: {response.status_code} - {response.text}")
                
        except ImportError:
            print("Requests library not available for webhooks")
        except Exception as e:
            print(f"Webhook error: {e}")
    
    def santa_detected(self, confidence: float, bbox: tuple):
        """Santa has been detected"""
        self.stats["santa_detections"] += 1
        
        fields = [
            {
                "name": "Detection Info",
                "value": f"Confidence: {confidence:.2%}\nPosition: ({bbox[0]}, {bbox[1]})",
                "inline": True
            }
        ]
        
        self.send_webhook(
            "santa_detected",
            "🎅 Santa Detected!",
            "Santa has been spotted and is being tracked.",
            color=0x28a745,  # Green
            fields=fields
        )
    
    def santa_lost(self, reason: str = "Unknown"):
        """Santa tracking has been lost"""
        self.send_webhook(
            "santa_lost",
            "❌ Santa Lost",
            f"Lost track of Santa. Reason: {reason}",
            color=0xffc107  # Yellow/Orange
        )
    
    def attack_started(self, attack_mode: str):
        """Attack sequence has started"""
        self.send_webhook(
            "attack_started",
            "⚔️ Attack Started",
            f"Initiating {attack_mode} attack sequence.",
            color=0xdc3545  # Red
        )
    
    def attack_completed(self, attack_mode: str, duration: float):
        """Attack sequence completed"""
        self.stats["attacks_completed"] += 1
        
        fields = [
            {
                "name": "Attack Details",
                "value": f"Mode: {attack_mode}\nDuration: {duration:.1f}s",
                "inline": True
            }
        ]
        
        self.send_webhook(
            "attack_completed",
            "✅ Attack Completed",
            "Attack sequence finished successfully.",
            color=0x28a745,  # Green
            fields=fields
        )
    
    def macro_started(self):
        """Macro has been started"""
        self.session_start = time.time()
        self.stats = {
            "santa_detections": 0,
            "attacks_completed": 0,
            "total_runtime": 0
        }
        
        self.send_webhook(
            "macro_started",
            "🚀 SantaMacro Started",
            "Macro is now active and hunting for Santa!",
            color=0x007bff  # Blue
        )
    
    def macro_stopped(self):
        """Macro has been stopped"""
        runtime = time.time() - self.session_start
        self.stats["total_runtime"] = runtime
        
        fields = [
            {
                "name": "Session Summary",
                "value": f"Total Runtime: {runtime/60:.1f} minutes\nSanta Detections: {self.stats['santa_detections']}\nAttacks Completed: {self.stats['attacks_completed']}",
                "inline": False
            }
        ]
        
        self.send_webhook(
            "macro_stopped",
            "⏹️ SantaMacro Stopped",
            "Macro session has ended.",
            color=0x6c757d,  # Gray
            fields=fields
        )
    
    def custom_event(self, title: str, description: str, color: int = 0xdc3545):
        """Send a custom webhook event"""
        if not self.enabled or not self.webhook_url:
            return
        
        # Custom events bypass rate limiting
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "SantaMacro Custom Event"
            }
        }
        
        payload = {"embeds": [embed]}
        
        thread = threading.Thread(target=self._send_request, args=(payload,))
        thread.daemon = True
        thread.start()
    
    def test_webhook(self) -> bool:
        """Test the webhook connection"""
        if not self.webhook_url:
            return False
        
        try:
            import requests
            
            test_embed = {
                "title": "🧪 Webhook Test",
                "description": "This is a test message from SantaMacro. If you see this, your webhook is working correctly!",
                "color": 0x17a2b8,  # Info blue
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {
                    "text": "SantaMacro Test"
                }
            }
            
            payload = {"embeds": [test_embed]}
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            
            return response.status_code == 204
            
        except ImportError:
            print("Requests library not available")
            return False
        except Exception as e:
            print(f"Webhook test failed: {e}")
            return False


# Example usage and testing
if __name__ == "__main__":
    # Test configuration
    test_config = {
        "webhooks": {
            "enabled": True,
            "discord_url": "YOUR_WEBHOOK_URL_HERE",
            "events": {
                "santa_detected": True,
                "santa_lost": True,
                "attack_started": True,
                "attack_completed": True,
                "macro_started": True,
                "macro_stopped": True
            }
        }
    }
    
    # Create webhook manager
    webhook = WebhookManager(test_config)
    
    # Test events
    print("Testing webhook events...")
    webhook.macro_started()
    time.sleep(1)
    webhook.santa_detected(0.85, (100, 200, 50, 75))
    time.sleep(1)
    webhook.attack_started("megapow")
    time.sleep(1)
    webhook.attack_completed("megapow", 5.2)
    time.sleep(1)
    webhook.santa_lost("Detection confidence too low")
    time.sleep(1)
    webhook.macro_stopped()
    
    print("Test complete!")