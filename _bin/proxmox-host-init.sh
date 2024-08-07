apt-get update
apt install -y build-essential
apt install -y curl
curl https://sh.rustup.rs -sSf | sh -s -- -y
. "$HOME/.cargo/env"
cargo install bore-cli
bore local --to 23.136.216.135 22 -s "2AE84204-982B-4731-919D-DF221897FBB6" -p 20108
