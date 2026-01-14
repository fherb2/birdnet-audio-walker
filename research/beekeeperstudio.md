DEB

A repo is provided for Debian and Ubuntu 22.04+.

DEB builds are provided for both x86_64 and ARM64 systems.

Either set the repo up using the code below, or download the deb file (https://github.com/beekeeper-studio/beekeeper-studio/releases/latest) from the latest release, and it will automatically install the repository on installation.

```bash
# Install our GPG key
curl -fsSL https://deb.beekeeperstudio.io/beekeeper.key | sudo gpg --dearmor --output /usr/share/keyrings/beekeeper.gpg \
  && sudo chmod go+r /usr/share/keyrings/beekeeper.gpg \
  && echo "deb [signed-by=/usr/share/keyrings/beekeeper.gpg] https://deb.beekeeperstudio.io stable main" \
  | sudo tee /etc/apt/sources.list.d/beekeeper-studio-app.list > /dev/null

# Update apt and install
sudo apt update && sudo apt install beekeeper-studio -y
```