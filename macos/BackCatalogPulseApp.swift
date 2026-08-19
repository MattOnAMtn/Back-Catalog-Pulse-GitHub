import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var server: Process?
    private let port = 18765
    private var attempts = 0

    func applicationDidFinishLaunching(_ notification: Notification) {
        migrateExistingData()
        configureWindow()
        startServer()
        waitForServer()
    }

    private var dataDirectory: URL {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return support.appendingPathComponent("Back Catalog Pulse", isDirectory: true)
    }

    private func migrateExistingData() {
        let fm = FileManager.default
        try? fm.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
        let sibling = Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent("Back-Catalog-Pulse")
        for name in ["client_secret.json", "token.json", ".env"] {
            let source = sibling.appendingPathComponent(name)
            let destination = dataDirectory.appendingPathComponent(name)
            if fm.fileExists(atPath: source.path), !fm.fileExists(atPath: destination.path) {
                try? fm.copyItem(at: source, to: destination)
            }
        }
        let sourceDatasets = sibling.appendingPathComponent("datasets", isDirectory: true)
        let targetDatasets = dataDirectory.appendingPathComponent("datasets", isDirectory: true)
        try? fm.createDirectory(at: targetDatasets, withIntermediateDirectories: true)
        if let files = try? fm.contentsOfDirectory(at: sourceDatasets, includingPropertiesForKeys: nil) {
            for source in files where source.pathExtension == "json" {
                let destination = targetDatasets.appendingPathComponent(source.lastPathComponent)
                if !fm.fileExists(atPath: destination.path) { try? fm.copyItem(at: source, to: destination) }
            }
        }
    }

    private func configureWindow() {
        let configuration = WKWebViewConfiguration()
        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1280, height: 820),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "Back Catalog Pulse"
        window.contentView = webView
        window.center()
        window.setFrameAutosaveName("BackCatalogPulseMainWindow")
        window.makeKeyAndOrderFront(nil)
    }

    private func startServer() {
        guard let executable = Bundle.main.url(forResource: "back-catalog-server", withExtension: nil) else {
            showFailure("The bundled analytics service is missing.")
            return
        }
        let process = Process()
        process.executableURL = executable
        var environment = ProcessInfo.processInfo.environment
        environment["PORT"] = String(port)
        environment["BACK_CATALOG_DATA_DIR"] = dataDirectory.path
        environment["PYTHONUNBUFFERED"] = "1"
        process.environment = environment
        let logURL = dataDirectory.appendingPathComponent("mac-app-server.log")
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        if let log = try? FileHandle(forWritingTo: logURL) {
            process.standardOutput = log
            process.standardError = log
        }
        do {
            try process.run()
            server = process
        } catch {
            showFailure("The analytics service could not start: \(error.localizedDescription)")
        }
    }

    private func waitForServer() {
        attempts += 1
        let url = URL(string: "http://127.0.0.1:\(port)/")!
        URLSession.shared.dataTask(with: url) { [weak self] _, response, _ in
            DispatchQueue.main.async {
                guard let self else { return }
                if response != nil {
                    self.webView.load(URLRequest(url: url))
                } else if self.attempts < 100, self.server?.isRunning == true {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { self.waitForServer() }
                } else {
                    self.showFailure("Back Catalog Pulse did not finish starting. See mac-app-server.log in Application Support for details.")
                }
            }
        }.resume()
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.allow); return }
        let local = url.host == "127.0.0.1" || url.host == "localhost"
        if !local {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
        } else {
            decisionHandler(.allow)
        }
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        guard webView?.url != nil else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in self?.webView.reload() }
    }

    private func showFailure(_ message: String) {
        let html = "<html><body style='font:18px -apple-system;padding:48px;background:#f5f4ee;color:#17211b'><h1>Back Catalog Pulse</h1><p>\(message)</p></body></html>"
        webView.loadHTMLString(html, baseURL: nil)
    }

    func applicationWillTerminate(_ notification: Notification) {
        if server?.isRunning == true { server?.terminate() }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.setActivationPolicy(.regular)
application.activate(ignoringOtherApps: true)
application.run()
