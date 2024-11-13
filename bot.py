from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from datetime import datetime
import os
from config import MEETING_URL, BOT_NAME

class JitsiBot:
    def __init__(self):
        self.options = Options()
        
        # Add required Chrome options
        self.options.add_argument("--use-fake-ui-for-media-stream")
        self.options.add_argument("--use-file-for-fake-audio-capture")
        self.options.add_argument("--allow-file-access")
        self.options.add_argument("--enable-experimental-web-platform-features")
        self.options.add_argument("--autoplay-policy=no-user-gesture-required")
        self.options.add_argument("--disable-web-security")
        self.options.add_argument("--allow-running-insecure-content")
        self.options.add_argument("--start-maximized")
        self.options.add_argument("--disable-infobars")
        self.options.add_argument("--disable-notifications")
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument("--use-fake-device-for-media-stream")
        
        # Enable audio recording
        self.options.add_argument("--enable-usermedia-screen-capturing")
        self.options.add_argument("--allow-file-access-from-files")
        
        # Add experimental options
        self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.options.add_experimental_option('useAutomationExtension', False)
        self.options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.media_stream_mic": 1,
            "profile.default_content_setting_values.media_stream_camera": 1,
            "download.default_directory": os.path.join(os.getcwd(), "recordings")
        })

        # Configure selenium-wire to capture media
        seleniumwire_options = {
            'enable_har': True,
            'har_options': {
                'captureHeaders': True,
                'captureContent': True
            }
        }

        self.driver = webdriver.Chrome(
            options=self.options,
            seleniumwire_options=seleniumwire_options
        )
        
    def join_meeting(self):
        try:
            print(f"Joining meeting at: {MEETING_URL}")
            self.driver.get(MEETING_URL)
            
            # Click join button using the data-testid
            join_button = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='prejoin.joinMeeting']"))
            )
            join_button.click()
            print("Clicked join button")
            
            # Wait for join completion
            print("Waiting for meeting join completion...")
            max_attempts = 30
            for attempt in range(max_attempts):
                join_status = self.driver.execute_script("""
                    if (window.APP && window.APP.conference && window.APP.conference._room) {
                        return {
                            isJoined: window.APP.conference._room.isJoined(),
                            participants: window.APP.conference._room.getParticipants().length,
                            hasAudio: !!window.APP.conference._room.getLocalAudioTrack()
                        };
                    }
                    return null;
                """)
                
                if join_status and join_status['isJoined']:
                    print(f"Successfully joined the meeting. Status: {join_status}")
                    break
                    
                time.sleep(1)
                print(f"Waiting for join completion... attempt {attempt + 1}/{max_attempts}")
            else:
                raise Exception("Failed to fully join the meeting")
            
            # Additional wait for audio setup
            time.sleep(5)
            print("Starting recording...")
            
            # Start recording
            self.start_recording()
            
            # Keep the bot in the meeting and monitor status
            while True:
                meeting_status = self.driver.execute_script("""
                    return {
                        isJoined: window.APP.conference._room.isJoined(),
                        participants: window.APP.conference._room.getParticipants().length,
                        hasAudio: !!window.APP.conference._room.getLocalAudioTrack(),
                        recordingStatus: window.mediaRecorder ? window.mediaRecorder.state : 'not_found',
                        chunksRecorded: window.audioChunks ? window.audioChunks.length : 0
                    };
                """)
                print(f"Meeting status: {meeting_status}")
                time.sleep(10)
                
        except Exception as e:
            print(f"Error in join_meeting: {e}")
            self.driver.quit()
            
    def start_recording(self):
        try:
            recordings_dir = os.path.join(os.getcwd(), "recordings")
            if not os.path.exists(recordings_dir):
                os.makedirs(recordings_dir)
                print(f"Created recordings directory at: {recordings_dir}")

            recording_script = '''
            try {
                const conference = window.APP.conference._room;
                console.log("Setting up recording...");
                
                // Create audio context and destination
                const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                const destination = audioContext.createMediaStreamDestination();
                window.audioContext = audioContext;
                
                // Initialize audio chunks array
                window.audioChunks = [];
                
                let tracksAdded = 0;
                
                // Function to get audio stream from participant
                const getParticipantAudioStream = (participant) => {
                    const tracks = participant.getTracks();
                    const audioTrack = tracks.find(t => t.getType() === 'audio');
                    return audioTrack ? audioTrack.stream : null;
                };

                // Function to add stream to recording
                const addStreamToRecording = (stream) => {
                    if (stream && stream.getAudioTracks().length > 0) {
                        const source = audioContext.createMediaStreamSource(stream);
                        const gainNode = audioContext.createGain();
                        gainNode.gain.value = 1.0;  // Adjust volume if needed
                        source.connect(gainNode);
                        gainNode.connect(destination);
                        console.log('Added audio stream to recording');
                        return true;
                    }
                    return false;
                };

                // Add remote participants' audio
                conference.getParticipants().forEach(participant => {
                    const stream = getParticipantAudioStream(participant);
                    if (stream) {
                        if (addStreamToRecording(stream)) {
                            tracksAdded++;
                            console.log(`Added audio for participant: ${participant.getId()}`);
                        }
                    }
                });

                // Create a combined stream for recording
                const combinedStream = destination.stream;
                console.log(`Combined stream tracks: ${combinedStream.getAudioTracks().length}`);

                // Set up MediaRecorder
                window.mediaRecorder = new MediaRecorder(combinedStream, {
                    mimeType: 'audio/webm;codecs=opus',
                    audioBitsPerSecond: 128000
                });

                window.mediaRecorder.ondataavailable = (event) => {
                    console.log(`Data available event, size: ${event.data.size}`);
                    if (event.data.size > 0) {
                        window.audioChunks.push(event.data);
                    }
                };

                window.mediaRecorder.onstop = () => {
                    console.log('MediaRecorder stopped, processing chunks...');
                    if (window.audioChunks.length > 0) {
                        const blob = new Blob(window.audioChunks, { type: 'audio/webm' });
                        console.log(`Creating blob of size: ${blob.size}`);
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                        a.href = url;
                        a.download = `meeting_recording_${timestamp}.webm`;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        console.log(`Recording saved with ${window.audioChunks.length} chunks`);
                    } else {
                        console.log('No audio chunks recorded');
                    }
                };

                // Handle new participants
                conference.on('track.added', (track) => {
                    if (track.getType() === 'audio' && track.stream) {
                        if (addStreamToRecording(track.stream)) {
                            tracksAdded++;
                            console.log('New audio track added to recording');
                        }
                    }
                });

                // Start recording with smaller chunks for more frequent saves
                window.mediaRecorder.start(500);  // Create chunks every 500ms
                console.log("MediaRecorder started");

                return {
                    status: 'started',
                    tracksAdded: tracksAdded,
                    recorderState: window.mediaRecorder.state,
                    streamTracks: combinedStream.getAudioTracks().length
                };
            } catch (error) {
                console.error('Recording setup error:', error);
                return {
                    status: 'error',
                    error: error.toString()
                };
            }
            '''
            
            result = self.driver.execute_script(recording_script)
            print(f"Recording setup result: {result}")
            
            # Monitor initial recording status
            for i in range(5):  # Check status multiple times
                status = self.driver.execute_script("""
                    return {
                        recorderState: window.mediaRecorder ? window.mediaRecorder.state : 'not_found',
                        chunksCount: window.audioChunks ? window.audioChunks.length : 0,
                        hasAudioTracks: window.mediaRecorder ? 
                            window.mediaRecorder.stream.getAudioTracks().length : 0,
                        participantCount: window.APP.conference._room.getParticipants().length,
                        lastChunkSize: window.audioChunks && window.audioChunks.length > 0 ? 
                            window.audioChunks[window.audioChunks.length - 1].size : 0
                    };
                """)
                print(f"Recording status check {i+1}: {status}")
                time.sleep(1)
                
        except Exception as e:
            print(f"Error starting recording: {e}")
            import traceback
            print(traceback.format_exc())

    def stop_recording(self):
        try:
            stop_script = """
            try {
                if (window.mediaRecorder && window.mediaRecorder.state !== 'inactive') {
                    console.log('Stopping MediaRecorder...');
                    window.mediaRecorder.stop();
                    
                    // Force save current chunks if any exist
                    if (window.audioChunks && window.audioChunks.length > 0) {
                        const blob = new Blob(window.audioChunks, { type: 'audio/webm' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                        a.href = url;
                        a.download = `meeting_recording_${timestamp}.webm`;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        console.log(`Final recording saved with ${window.audioChunks.length} chunks`);
                    }
                    
                    if (window.audioContext) {
                        window.audioContext.close();
                    }
                    return true;
                }
                return false;
            } catch (error) {
                console.error('Error stopping recording:', error);
                return false;
            }
            """
            stopped = self.driver.execute_script(stop_script)
            time.sleep(3)  # Give time for the file to save
            print(f"Recording {'stopped' if stopped else 'was already stopped'}")
        except Exception as e:
            print(f"Error stopping recording: {e}")
        
    def quit(self):
        try:
            print("\nShutting down bot...")
            self.stop_recording()
            time.sleep(3)  # Give more time for the recording to save
            self.driver.quit()
            print("Bot shutdown complete")
        except Exception as e:
            print("Bot shutdown complete (browser already closed)")

def main():
    bot = JitsiBot()
    print("\nBot Instructions:")
    print("1. Bot will automatically join the meeting and start recording")
    print("2. Recordings will be saved in the 'recordings' folder")
    print("3. Press Ctrl+C to stop recording and exit")
    print("\nStarting bot...\n")
    try:
        bot.join_meeting()
    except KeyboardInterrupt:
        print("\nStopping bot...")
        bot.quit()

if __name__ == "__main__":
    main()