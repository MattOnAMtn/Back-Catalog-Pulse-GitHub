# Back Catalog Pulse for macOS

This target packages the existing local Flask application inside a native macOS WebKit window. The Python service runs only on the Mac's loopback interface and stops when the app quits.

On first launch, the app copies credentials and saved datasets from a neighboring `Back-Catalog-Pulse` folder into `~/Library/Application Support/Back Catalog Pulse`. Subsequent versions reuse that persistent data.

The application is ad-hoc signed for personal testing. Public distribution requires an Apple Developer ID signature and notarization.
