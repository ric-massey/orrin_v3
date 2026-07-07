# Adding a Custom Peer

Step-by-step
1. Create class inheriting from peers.PeerBase
2. Implement should_wake(context) and propose(context)
3. Add tests for proposal filtering and integration
4. Register peer in peers/registry

Example
- See brain/peers/examples/architect.py for a canonical pattern.
