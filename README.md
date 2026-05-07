The project is renamed to **birdnet-copter**.

The project has been renamed to "birdnet-copter". The term “helicopter” is used here as a synonym for the tool that allows you to scan your environmental audio recordings to identify and analyze specific bird calls.

# Birdnet-Copter

This application focuses on the following features:

* Use the GPU to analyze large volumes of environmental recordings using the BirdNET model. However, it also allows the CPU as an alternative if a suitable GPU is not available.
* Organize your audio recordings in the file system by device, recording location, and recording period.
* Analyze any selectable sections of this structure
* Add additional information to your recording details (device/location/time period)
* (more features are planned...)
* Use the software on any system, including high-performance GPU systems, without installing more than a graphics card driver: a ready-to-use Docker image with all components.

# Project state

Coming soon:

- ready to use Docker images (audio file analysis with birdnet whith CUDA/GPU support; other
- mass analysis into SQLite databases (productive)
- acoutic validating of database entries (development; cli and with an audio announcement of the audio snippet currently being played)
  - use via Web Interface, to be independing on the place of the powerfull high performance system
