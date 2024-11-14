from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import speech_recognition as sr
import threading
from config import MEETING_URL, BOT_NAME

class JitsiBot:
    def __init__(self):
        self.options = Options()
        
        # Add required Chrome options
        self.options.add_argument("--headless")  # Enable headless mode
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
        
        self.recognizer = sr.Recognizer()  # Initialize the recognizer
        self.transcription_thread = None  # Thread for transcription

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
        
        self.participants = {}  # Dictionary to keep track of participants
        self.current_speaker = None  # Variable to track the current speaker

    def join_meeting(self):
        try:
            print(f"Joining meeting at: {MEETING_URL}")
            self.driver.get(MEETING_URL)
            
            # Wait for the name input field to be present and enter the bot's name
            name_input = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#premeeting-name-input"))
            )
            name_input.clear()  # Clear any existing text
            name_input.send_keys(BOT_NAME)  # Enter the bot's name
            print(f"Entered bot name: {BOT_NAME}")
            
            # Disable the video button
            video_button = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".toolbox-button[aria-label='Stop camera']"))
            )
            video_button.click()  # Click to disable the video
            print("Disabled video button")
            
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
                    
                    # Hide all visual elements
                    self.driver.execute_script("""
                        const checkConferenceReady = setInterval(() => {
                            if (window.APP && window.APP.conference && window.APP.conference._room) {
                                clearInterval(checkConferenceReady);
                                
                                const videoElements = document.querySelectorAll('video');
                                videoElements.forEach(video => {
                                    video.style.display = 'none';  // Hide video elements
                                });

                                const localParticipant = window.APP.conference._room.getLocalParticipant();
                                const botName = localParticipant.getDisplayName();
                                const participantElements = document.querySelectorAll('.participant');

                                participantElements.forEach(element => {
                                    if (!element.innerText.includes(botName)) {
                                        element.style.display = 'none';
                                    }
                                });
                            }
                        }, 1000);  // Check every 100ms
                    """)
                    
                    break
                    
                time.sleep(1)
                print(f"Waiting for join completion... attempt {attempt + 1}/{max_attempts}")
            else:
                raise Exception("Failed to fully join the meeting")
            
            # Additional wait for audio setup
            time.sleep(5)
            print("Starting transcription...")

            # Start the transcription in a separate thread
            self.start_transcription()
            
            #time.sleep(5)
            #print("Starting recording...")
            # Start recording
            #self.start_recording()
            
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
    
    def start_transcription(self):
        """Start a thread to capture and transcribe audio."""
        self.transcription_thread = threading.Thread(target=self.transcribe_audio)
        self.transcription_thread.start()

    def transcribe_audio(self):
        """Capture audio and transcribe it in real-time."""
        with sr.Microphone() as source:
            print("Listening for audio...")
            while True:
                try:
                    # Adjust for ambient noise and listen for audio
                    self.recognizer.adjust_for_ambient_noise(source)
                    audio = self.recognizer.listen(source, timeout=5)  # Listen for audio
                    print("Recognizing...")
                    # Use Google Web Speech API to transcribe audio
                    text = self.recognizer.recognize_google(audio)

                    # Get the current speaker's name from the DOM
                    current_speaker_name = self.driver.execute_script("""
                        const nameElement = document.querySelector('#localDisplayName');
                        return nameElement ? nameElement.innerText : 'Unknown Speaker';
                    """)

                    # Log the transcription with participant name
                    log_entry = f"{current_speaker_name}: {text}"
                    print(log_entry)  # Print the transcription
                    with open("transcript.txt", "a") as f:
                        f.write(log_entry + "\n")  # Log the transcription to a file

                except sr.WaitTimeoutError:
                    print("Listening timed out while waiting for phrase to start")
                except sr.UnknownValueError:
                    print("Google Speech Recognition could not understand audio")
                except sr.RequestError as e:
                    print(f"Could not request results from Google Speech Recognition service; {e}")
                except Exception as e:
                    print(f"Error during transcription: {e}")

    def identify_speaker(self, participant_id):
        """Identify the speaker based on participant ID."""
        # Assuming you have a mapping of participant IDs to names
        if participant_id in self.participants:
            self.current_speaker = self.participants[participant_id]  # Get the name from the mapping
        else:
            self.current_speaker = "Unknown Speaker"

    def stop_transcription(self):
        """Stop the transcription thread."""
        if self.transcription_thread is not None:
            self.transcription_thread.join()

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
                
                // Function to add stream to recording
                const addStreamToRecording = (stream, participantName) => {
                    if (stream && stream.getAudioTracks().length > 0) {
                        const source = audioContext.createMediaStreamSource(stream);
                        const gainNode = audioContext.createGain();
                        gainNode.gain.value = 1.0;  // Adjust volume if needed
                        source.connect(gainNode);
                        gainNode.connect(destination);
                        console.log('Added audio stream to recording for participant: ' + participantName);
                        return true;
                    }
                    return false;
                };

                // Add remote participants' audio
                conference.getParticipants().forEach(participant => {
                    const stream = participant.getTracks().find(t => t.getType() === 'audio')?.stream;
                    if (stream) {
                        const participantName = participant.getDisplayName();
                        addStreamToRecording(stream, participantName);
                    }
                });

                // Set up MediaRecorder
                const combinedStream = destination.stream;
                window.mediaRecorder = new MediaRecorder(combinedStream, {
                    mimeType: 'audio/webm;codecs=opus',
                    audioBitsPerSecond: 128000
                });

                window.mediaRecorder.ondataavailable = (event) => {
                    if (event.data.size > 0) {
                        window.audioChunks.push(event.data);
                    }
                };

                window.mediaRecorder.onstop = () => {
                    console.log('MediaRecorder stopped, processing chunks...');
                    if (window.audioChunks.length > 0) {
                        const blob = new Blob(window.audioChunks, { type: 'audio/webm' });
                        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                        const filePath = `${recordings_dir}/meeting_recording_${timestamp}.webm`;
                        const fileReader = new FileReader();
                        fileReader.onload = function() {
                            const arrayBuffer = this.result;
                            const buffer = new Uint8Array(arrayBuffer);
                            const fs = require('fs');
                            fs.writeFileSync(filePath, buffer);
                            console.log(`Recording saved at: ${filePath}`);
                        };
                        fileReader.readAsArrayBuffer(blob);
                    } else {
                        console.log('No audio chunks recorded');
                    }
                };

                // Start recording
                window.mediaRecorder.start(5000);  // Create chunks every 5000ms
                console.log("MediaRecorder started");

                return {
                    status: 'started',
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
                        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                        const filePath = `${recordings_dir}/meeting_recording_${timestamp}.webm`;
                        
                        // Create a FileReader to read the Blob
                        const fileReader = new FileReader();
                        fileReader.onload = function() {
                            const arrayBuffer = this.result;
                            const buffer = new Uint8Array(arrayBuffer);
                            const fs = require('fs');
                            fs.writeFileSync(filePath, buffer);
                            console.log(`Recording saved at: ${filePath}`);
                        };
                        fileReader.readAsArrayBuffer(blob);
                    } else {
                        console.log('No audio chunks recorded');
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
            
            # Execute the stop script
            stopped = self.driver.execute_script(stop_script)
            time.sleep(3)  # Give time for the file to save
            print(f"Recording {'stopped' if stopped else 'was already stopped'}")
        except Exception as e:
            print(f"Error stopping recording: {e}")
        
    def quit(self):
        try:
            print("\nShutting down bot...")
            self.stop_transcription()  # Stop the transcription thread
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
    finally:
        # Ensure that the transcription thread is stopped if it is still running
        if bot.transcription_thread is not None and bot.transcription_thread.is_alive():
            bot.stop_transcription()

if __name__ == "__main__":
    main()