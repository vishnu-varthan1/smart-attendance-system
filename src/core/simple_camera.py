#!/usr/bin/env python3
"""
Simple Camera Module for Attendance System
Basic camera functionality with OpenCV support
"""

import threading
import time
import logging
from datetime import datetime

# Try to import cv2 with error handling
try:
    import cv2
    CV2_AVAILABLE = True
    print("✅ OpenCV available for camera operations")
except ImportError as e:
    print(f"❌ OpenCV not available: {e}")
    CV2_AVAILABLE = False
    cv2 = None

class SimpleCamera:
    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.cap = None
        self.is_running = False
        self.current_frame = None
        self.lock = threading.Lock()
        self.capture_thread = None
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
    
    def __del__(self):
        """Destructor to ensure camera resources are cleaned up"""
        try:
            if hasattr(self, 'is_running') and self.is_running:
                self.stop_camera()
        except Exception as e:
            # Use print instead of logger as logger might not be available during destruction
            print(f"Error during SimpleCamera cleanup: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure cleanup"""
        try:
            if self.is_running:
                self.stop_camera()
        except Exception as e:
            self.logger.error(f"Error during context manager cleanup: {e}")
        return False  # Don't suppress exceptions
    
    def _cleanup_camera(self):
        """Safely cleanup camera resources"""
        try:
            if self.cap is not None:
                if self.cap.isOpened():
                    self.cap.release()
                self.cap = None
                self.logger.debug("Camera resources cleaned up")
        except Exception as e:
            self.logger.error(f"Error during camera cleanup: {str(e)}")
            self.cap = None  # Force reset even if release fails
        
    def start_camera(self):
        """Start camera capture with proper resource management"""
        try:
            if not CV2_AVAILABLE:
                self.logger.error("OpenCV not available - cannot start camera")
                return False
                
            if self.is_running:
                self.logger.info("Camera already running")
                return True
            
            # Ensure any previous camera is released
            self._cleanup_camera()
                
            # Try to initialize camera
            self.cap = cv2.VideoCapture(self.camera_index)
            
            if not self.cap.isOpened():
                self.logger.error(f"Failed to open camera {self.camera_index}")
                # Try alternative camera indices
                for alt_index in [1, 2, 0]:
                    if alt_index != self.camera_index:
                        self.logger.info(f"Trying camera index {alt_index}")
                        self._cleanup_camera()  # Clean up failed attempt
                        self.cap = cv2.VideoCapture(alt_index)
                        if self.cap.isOpened():
                            self.camera_index = alt_index
                            self.logger.info(f"Successfully opened camera {alt_index}")
                            break
                else:
                    self.logger.error("No working camera found")
                    self._cleanup_camera()
                    return False
            
            # Set camera properties
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            
            # Test camera by reading a frame
            ret, test_frame = self.cap.read()
            if not ret:
                self.logger.error("Camera opened but cannot read frames")
                self._cleanup_camera()
                return False
            
            self.is_running = True
            
            # Start capture thread
            try:
                self.capture_thread = threading.Thread(target=self._capture_frames)
                self.capture_thread.daemon = True
                self.capture_thread.start()
                
                self.logger.info(f"Camera {self.camera_index} started successfully")
                return True
                
            except Exception as thread_error:
                self.logger.error(f"Failed to start capture thread: {str(thread_error)}")
                self.is_running = False
                self._cleanup_camera()
                return False
            
        except Exception as e:
            self.logger.error(f"Error starting camera: {str(e)}")
            self._cleanup_camera()
            return False
    
    def stop_camera(self):
        """Stop camera capture with proper resource cleanup"""
        try:
            # Signal the capture thread to stop
            self.is_running = False
            
            # Wait for capture thread to finish
            if self.capture_thread and self.capture_thread.is_alive():
                self.capture_thread.join(timeout=3)
                if self.capture_thread.is_alive():
                    self.logger.warning("Capture thread did not stop gracefully")
            
            # Clean up camera resources
            self._cleanup_camera()
            
            # Clear current frame
            with self.lock:
                self.current_frame = None
            
            self.capture_thread = None
            self.logger.info("Camera stopped successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping camera: {str(e)}")
            # Force cleanup even if there were errors
            self.is_running = False
            self._cleanup_camera()
            with self.lock:
                self.current_frame = None
            return False
    
    def _capture_frames(self):
        """Capture frames in background thread with proper error handling"""
        frame_read_failures = 0
        max_failures = 10  # Allow some failures before giving up
        
        try:
            while self.is_running and self.cap and self.cap.isOpened():
                try:
                    ret, frame = self.cap.read()
                    
                    if ret:
                        # Reset failure counter on successful read
                        frame_read_failures = 0
                        
                        with self.lock:
                            self.current_frame = frame.copy()
                    else:
                        frame_read_failures += 1
                        self.logger.warning(f"Failed to read frame from camera (attempt {frame_read_failures})")
                        
                        if frame_read_failures >= max_failures:
                            self.logger.error("Too many frame read failures, stopping capture")
                            break
                            
                        time.sleep(0.1)
                        continue
                        
                    time.sleep(0.033)  # ~30 FPS
                    
                except Exception as frame_error:
                    self.logger.error(f"Error processing frame in capture thread: {str(frame_error)}")
                    time.sleep(0.1)  # Brief pause before retrying
                    continue
                    
        except Exception as capture_error:
            self.logger.error(f"Critical error in capture thread: {str(capture_error)}")
        finally:
            # Ensure cleanup happens even if there are exceptions
            try:
                self.logger.info("Capture thread ending, cleaning up")
                self.is_running = False
                
                # Clear current frame
                with self.lock:
                    self.current_frame = None
                    
            except Exception as cleanup_error:
                self.logger.error(f"Error during capture thread cleanup: {str(cleanup_error)}")
            
            self.logger.info("Capture thread terminated")
    
    def get_frame(self):
        """Get current frame"""
        with self.lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
            return None
    
    def get_frame_with_overlay(self):
        """Get frame with simple overlay"""
        frame = self.get_frame()
        
        if frame is not None:
            # Add timestamp overlay
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(frame, timestamp, (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Add status overlay
            status_text = "Camera Active - Manual Attendance Mode"
            cv2.putText(frame, status_text, (10, frame.shape[0] - 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # Add simple border
            cv2.rectangle(frame, (5, 5), (frame.shape[1]-5, frame.shape[0]-5), 
                         (0, 255, 0), 2)
        
        return frame
    
    def capture_photo(self, filename):
        """Capture and save a photo"""
        try:
            frame = self.get_frame()
            if frame is not None:
                cv2.imwrite(filename, frame)
                self.logger.info(f"Photo saved: {filename}")
                return True
            else:
                self.logger.error("No frame available for capture")
                return False
                
        except Exception as e:
            self.logger.error(f"Error capturing photo: {str(e)}")
            return False
    
    def is_camera_running(self):
        """Check if camera is running"""
        return self.is_running and self.cap is not None and self.cap.isOpened()

# Test the camera module
if __name__ == "__main__":
    print("Testing Simple Camera Module...")
    
    camera = SimpleCamera()
    
    if camera.start_camera():
        print("Camera started successfully!")
        
        # Test for 5 seconds
        for i in range(50):
            frame = camera.get_frame_with_overlay()
            if frame is not None:
                cv2.imshow('Test Camera', frame)
                if cv2.waitKey(100) & 0xFF == ord('q'):
                    break
            time.sleep(0.1)
        
        camera.stop_camera()
        cv2.destroyAllWindows()
        print("Camera test completed!")
    else:
        print("Failed to start camera!")