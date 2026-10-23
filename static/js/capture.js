document.querySelectorAll(".capture").forEach((box) => {
  const video = box.querySelector("video");
  const canvas = box.querySelector("canvas");
  const fileInput = box.querySelector('input[type="file"]');
  const status = document.createElement("p");
  status.className = "hint";
  status.textContent = "Camera is off.";
  box.appendChild(status);
  let stream = null;

  function stop() {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
    video.srcObject = null;
    video.hidden = true;
    if (!fileInput.files.length) {
      status.textContent = "Camera is off.";
    }
  }

  box.querySelector("[data-start]").addEventListener("click", async () => {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480 },
        audio: false,
      });
    } catch (error) {
      status.textContent = "This browser could not open the camera. Use an image file or the computer-camera button.";
      return;
    }
    video.srcObject = stream;
    video.hidden = false;
    status.textContent = "Camera is on for this capture only.";
  });

  box.querySelector("[data-stop]").addEventListener("click", stop);

  box.querySelector("[data-snap]").addEventListener("click", () => {
    if (!stream) {
      status.textContent = "Start the camera before capturing.";
      return;
    }
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      const file = new File([blob], "capture.jpg", { type: "image/jpeg" });
      const transfer = new DataTransfer();
      transfer.items.add(file);
      fileInput.files = transfer.files;
      stop();
      status.textContent = "One frame is ready. Submit the form to process it. The photo is not kept.";
    }, "image/jpeg", 0.92);
  });
});
