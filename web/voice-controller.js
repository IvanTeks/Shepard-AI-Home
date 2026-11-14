const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

function cleanForSpeech(value) {
  return String(value || "")
    .replace(/```[\s\S]*?```/g, " Code sample omitted. ")
    .replace(/https?:\/\/\S+/g, " link ")
    .replace(/[*_#>`|~]/g, " ")
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function speechChunks(value) {
  const text = cleanForSpeech(value);
  if (!text) return [];
  const sentences = text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [text];
  const chunks = [];
  let current = "";
  for (const sentence of sentences) {
    if (current && current.length + sentence.length > 260) {
      chunks.push(current.trim());
      current = "";
    }
    current += sentence;
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

export class ShepardVoiceController {
  constructor({ onNotice = () => {} } = {}) {
    this.onNotice = onNotice;
    this.recognition = null;
    this.activeButton = null;
    this.target = null;
    this.baseText = "";
    this.finalText = "";
    this.autoSpeak = localStorage.getItem("shepard-voice-auto-speak") === "true";
    this.autoSpeakButton = document.querySelector("#voice-auto-speak");
    this.status = document.querySelector("#voice-status");
  }

  attach() {
    document.querySelectorAll("[data-voice-mic]").forEach((button) => {
      button.addEventListener("click", () => this.toggleListening(button));
      if (!SpeechRecognition) {
        button.disabled = true;
        button.title = "Speech recognition is not available in this browser";
      }
    });
    this.autoSpeakButton?.addEventListener("click", () => {
      this.autoSpeak = !this.autoSpeak;
      localStorage.setItem("shepard-voice-auto-speak", String(this.autoSpeak));
      if (!this.autoSpeak) window.speechSynthesis?.cancel();
      this.renderAutoSpeak();
      this.setStatus(this.autoSpeak
        ? "Shepard will read new replies aloud. Press Speak at any time to interrupt."
        : "Read replies is off. Dictation still works with the Speak button.");
    });
    this.renderAutoSpeak();
    if (!SpeechRecognition) {
      this.setStatus("This browser cannot dictate yet. Typed chat still works; try current Chrome for browser speech support.");
    }
  }

  renderAutoSpeak() {
    if (!this.autoSpeakButton) return;
    this.autoSpeakButton.setAttribute("aria-pressed", String(this.autoSpeak));
    this.autoSpeakButton.classList.toggle("active", this.autoSpeak);
    const state = this.autoSpeakButton.querySelector("small");
    if (state) state.textContent = this.autoSpeak ? "On" : "Off";
  }

  setStatus(message) {
    if (this.status) this.status.textContent = message;
  }

  toggleListening(button) {
    if (this.activeButton === button && this.recognition) {
      this.stopListening();
      return;
    }
    this.startListening(button);
  }

  startListening(button) {
    if (!SpeechRecognition) {
      this.onNotice("Speech recognition is unavailable in this browser", true);
      return;
    }
    this.stopListening();
    window.speechSynthesis?.cancel();
    const target = document.querySelector(button.dataset.voiceTarget || "");
    if (!(target instanceof HTMLTextAreaElement || target instanceof HTMLInputElement)) return;

    const recognition = new SpeechRecognition();
    recognition.lang = document.documentElement.lang || navigator.language || "en-US";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 3;
    this.recognition = recognition;
    this.activeButton = button;
    this.target = target;
    this.baseText = target.value.trim();
    this.finalText = "";
    button.classList.add("listening");
    button.setAttribute("aria-pressed", "true");
    const label = button.querySelector("b");
    if (label) label.textContent = "Listening";
    this.setStatus("Listening… your untouched transcript will appear in the message box. Press again to stop.");

    recognition.onresult = (event) => {
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const transcript = event.results[index][0]?.transcript || "";
        if (event.results[index].isFinal) this.finalText += `${transcript.trim()} `;
        else interim += transcript;
      }
      target.value = [this.baseText, this.finalText.trim(), interim.trim()].filter(Boolean).join(" ");
      target.dispatchEvent(new Event("input", { bubbles: true }));
    };
    recognition.onerror = (event) => {
      const messages = {
        "not-allowed": "Microphone access was not allowed. Enable it for Shepard in your browser settings.",
        "audio-capture": "No working microphone was found.",
        "no-speech": "I didn’t catch any speech. Try again a little closer to the microphone."
      };
      this.setStatus(messages[event.error] || `Dictation stopped: ${event.error}.`);
    };
    recognition.onend = () => {
      const captured = this.finalText.trim();
      this.resetListeningState();
      if (captured) this.setStatus("Transcript ready. Review it, then choose Send—voice never skips the Gatekeeper.");
    };
    try {
      recognition.start();
      target.focus();
    } catch (error) {
      this.resetListeningState();
      this.onNotice(error.message || "Could not start the microphone", true);
    }
  }

  stopListening() {
    if (!this.recognition) return;
    const recognition = this.recognition;
    this.recognition = null;
    try { recognition.stop(); } catch {}
    this.resetListeningState();
  }

  resetListeningState() {
    const button = this.activeButton;
    if (button) {
      button.classList.remove("listening");
      button.setAttribute("aria-pressed", "false");
      const label = button.querySelector("b");
      if (label) label.textContent = "Speak";
    }
    this.activeButton = null;
    this.target = null;
    this.recognition = null;
  }

  speak(value) {
    if (!this.autoSpeak || !window.speechSynthesis) return;
    const chunks = speechChunks(value);
    if (!chunks.length) return;
    window.speechSynthesis.cancel();
    let index = 0;
    const next = () => {
      if (!this.autoSpeak || index >= chunks.length) {
        this.setStatus("Voice ready.");
        return;
      }
      const utterance = new SpeechSynthesisUtterance(chunks[index]);
      utterance.rate = 1.02;
      utterance.pitch = 0.96;
      utterance.onstart = () => this.setStatus("Shepard is speaking. Press Speak to interrupt and answer.");
      utterance.onend = () => { index += 1; next(); };
      utterance.onerror = () => this.setStatus("The system voice stopped. The written reply is still available.");
      window.speechSynthesis.speak(utterance);
    };
    next();
  }
}
