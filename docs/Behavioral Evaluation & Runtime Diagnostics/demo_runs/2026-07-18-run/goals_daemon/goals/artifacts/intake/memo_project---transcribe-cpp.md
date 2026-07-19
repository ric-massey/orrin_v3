# Research memo: Project - transcribe.cpp

Project - transcribe.cpp transcribe.cpp Apr 2026 - now I m super excited to share transcribe.cpp today. transcribe.cpp is a ggml based transcription library which supports all the latest transcription models.
Every model published under the handy-computer HF org
has been numerically validated and WER tested to match the reference implementation. It s accelerated everywhere. I m the author and maintainer of Handy . This library grew
from the pains of distributing a cross-platform speech-to-text application to many people. This is a v0.1.0 library which means that there are some rough edges which I
cannot discover alone! Please report them , and let s fix them together! Motivation Let me say this. I think distributing a cross-platform application with the current
ASR inference stack is terrible. You ve basically got whisper.cpp and ONNX. That s it. You could roll MLX
in for Apple devices, but now you ve to support two different engines and
port models to each. I ve been a fan of ONNX for getting model support into
Handy quickly, but so much performance is left on the table with CPU only. There are a few random libraries out there which claim to support a lot of models,
but they have unknown authors, and unknown testing, as far as I ve seen. They
leave me with more questions than answers. When will they stop maintaining this library? Has the creator thought
about bindings so you can actually use it in a real desktop or mobile app?
Is this effectively demo code? Have they benchmarked it? Is it faster
than ONNX? And this is what led to transcribe.cpp. As Handy s maintainer I needed
a library I could trust. Where I could download a file and run inference on it. Where
I can know that the inference coming from the model in the engine is as good as the
reference implementation. The inference should run on the GPU for the best performance.
It should be trivially embeddable in Handy, it cannot be a huge pytorch lib.
It must be something that works on Mac, Windows, and Linux. And ggml seemed like by far the best way forward. It has a strong community, and
a great distribution story. So what do you get? You get a fast and accurate inference engine with wide ranging model support. Support for 16 ASR Families (60+ models) with more coming Acceleration via Vulkan, Metal, CUDA, and TinyBLAS Every model has been numerically verified and WER tested Support for Streaming Transcription Support for Batch Transcription More or less drop in whisper.cpp replacement Maintainer supported bindings in 4 Languages Python Javascript/Typescript Rust ObjC/Swift Wide Model Support We intend to support as many state-of-the-art transcription models as possible.
As of today, we support most of the modern transcription models that are publicly available.
There are a few missing still, but they will be added soon. Acceleration Support One of my top goals was to run any ASR model I wanted on Vulkan. In my opinion
this is the floor for any application shipping local inference. For every

(read from: https://workshop.cjpais.com/projects/transcribe-cpp)

---
source: fetch_and_read
