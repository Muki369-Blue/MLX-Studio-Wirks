import AppKit
import SwiftUI
import WebKit

@main
struct MLXMoxyWirksApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var backend = BackendManager.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(backend)
                .frame(minWidth: 1100, minHeight: 760)
                .onAppear {
                    backend.start()
                }
        }
        .commands {
            CommandMenu("Moxy") {
                Button("Reload UI") {
                    backend.reloadWebView()
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("Restart Backend") {
                    backend.restart()
                }
                .keyboardShortcut("r", modifiers: [.command, .shift])

                Divider()

                Button("Open App Data") {
                    backend.openAppDataFolder()
                }

                Button("Open Logs") {
                    backend.openLogsFolder()
                }
            }
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func applicationWillTerminate(_ notification: Notification) {
        BackendManager.shared.stop()
    }
}

struct ContentView: View {
    @EnvironmentObject private var backend: BackendManager

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()

            switch backend.state {
            case .ready:
                MoxyWebView(url: backend.uiURL, reloadToken: backend.reloadToken)
            case .starting, .stopped:
                StatusView(
                    title: "Starting Moxy",
                    detail: "Launching the local backend on 127.0.0.1:\(backend.port)...",
                    isProgressVisible: true,
                    primaryAction: nil,
                    secondaryAction: nil
                )
            case .failed(let message):
                StatusView(
                    title: "Backend Unavailable",
                    detail: message,
                    isProgressVisible: false,
                    primaryAction: ("Retry", backend.restart),
                    secondaryAction: ("Open Logs", backend.openLogsFolder)
                )
            }
        }
    }

    private var toolbar: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(backend.state.statusColor)
                .frame(width: 10, height: 10)
            Text("MLX-Moxy-Wirks")
                .font(.headline)
            Text(backend.state.label)
                .foregroundStyle(.secondary)
                .font(.subheadline)
            Spacer()
            Button("Reload UI") {
                backend.reloadWebView()
            }
            .disabled(!backend.state.isReady)
            Button("Restart Backend") {
                backend.restart()
            }
            Button("Logs") {
                backend.openLogsFolder()
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(.bar)
    }
}

struct StatusView: View {
    let title: String
    let detail: String
    let isProgressVisible: Bool
    let primaryAction: (String, () -> Void)?
    let secondaryAction: (String, () -> Void)?

    var body: some View {
        VStack(spacing: 18) {
            if isProgressVisible {
                ProgressView()
                    .controlSize(.large)
            }

            Text(title)
                .font(.title2.weight(.semibold))

            Text(detail)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .frame(maxWidth: 520)

            HStack {
                if let primaryAction {
                    Button(primaryAction.0, action: primaryAction.1)
                        .keyboardShortcut(.defaultAction)
                }
                if let secondaryAction {
                    Button(secondaryAction.0, action: secondaryAction.1)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(32)
    }
}

struct MoxyWebView: NSViewRepresentable {
    let url: URL
    let reloadToken: Int

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.allowsBackForwardNavigationGestures = true
        webView.customUserAgent = "MLX-Moxy-Wirks-Mac"
        webView.load(URLRequest(url: url))
        context.coordinator.loadedToken = reloadToken
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        if context.coordinator.loadedToken != reloadToken {
            context.coordinator.loadedToken = reloadToken
            webView.load(URLRequest(url: url))
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    final class Coordinator {
        var loadedToken: Int = 0
    }
}

@MainActor
final class BackendManager: ObservableObject {
    static let shared = BackendManager()

    enum State: Equatable {
        case stopped
        case starting
        case ready
        case failed(String)

        var label: String {
            switch self {
            case .stopped: return "Stopped"
            case .starting: return "Starting"
            case .ready: return "Ready"
            case .failed: return "Needs Attention"
            }
        }

        var statusColor: Color {
            switch self {
            case .ready: return .green
            case .starting: return .yellow
            case .stopped: return .gray
            case .failed: return .red
            }
        }

        var isReady: Bool {
            self == .ready
        }
    }

    @Published private(set) var state: State = .stopped
    @Published private(set) var reloadToken: Int = 0

    let port = 8899
    private var process: Process?
    private var healthTask: Task<Void, Never>?
    private var logHandle: FileHandle?
    private let fileManager = FileManager.default
    private let authToken = UUID().uuidString.replacingOccurrences(of: "-", with: "")
        + UUID().uuidString.replacingOccurrences(of: "-", with: "")

    var uiURL: URL {
        var components = URLComponents()
        components.scheme = "http"
        components.host = "127.0.0.1"
        components.port = port
        components.queryItems = [
            URLQueryItem(name: "moxy_token", value: authToken)
        ]
        return components.url!
    }

    private var logsDirectory: URL {
        fileManager.homeDirectoryForCurrentUser
            .appendingPathComponent("Library", isDirectory: true)
            .appendingPathComponent("Logs", isDirectory: true)
            .appendingPathComponent("MLX-Moxy-Wirks", isDirectory: true)
    }

    private var appDataDirectory: URL {
        fileManager.homeDirectoryForCurrentUser
            .appendingPathComponent(".mlx_moxy_wirks", isDirectory: true)
    }

    func start() {
        guard process == nil else {
            return
        }

        do {
            let launch = try resolveBackendLaunch()
            try fileManager.createDirectory(at: logsDirectory, withIntermediateDirectories: true)
            let logURL = logsDirectory.appendingPathComponent("backend.log")
            if !fileManager.fileExists(atPath: logURL.path) {
                fileManager.createFile(atPath: logURL.path, contents: nil)
            }

            let handle = try FileHandle(forWritingTo: logURL)
            try handle.seekToEnd()
            logHandle = handle

            let proc = Process()
            proc.executableURL = launch.executableURL
            proc.arguments = launch.arguments
            proc.currentDirectoryURL = launch.currentDirectoryURL
            proc.environment = launch.environment
            proc.standardOutput = handle
            proc.standardError = handle

            state = .starting
            try proc.run()
            process = proc
            beginHealthPolling()
        } catch {
            state = .failed(error.localizedDescription)
            cleanupProcessState()
        }
    }

    func stop() {
        healthTask?.cancel()
        healthTask = nil

        if let process, process.isRunning {
            process.terminate()
            let deadline = Date().addingTimeInterval(3)
            while process.isRunning && Date() < deadline {
                Thread.sleep(forTimeInterval: 0.05)
            }
            if process.isRunning {
                process.interrupt()
            }
        }

        cleanupProcessState()
        state = .stopped
    }

    func restart() {
        stop()
        start()
    }

    func reloadWebView() {
        reloadToken += 1
    }

    func openLogsFolder() {
        try? fileManager.createDirectory(at: logsDirectory, withIntermediateDirectories: true)
        NSWorkspace.shared.open(logsDirectory)
    }

    func openAppDataFolder() {
        try? fileManager.createDirectory(at: appDataDirectory, withIntermediateDirectories: true)
        NSWorkspace.shared.open(appDataDirectory)
    }

    private func beginHealthPolling() {
        healthTask?.cancel()
        healthTask = Task { [weak self] in
            guard let self else { return }

            for _ in 0..<90 {
                if Task.isCancelled { return }
                if await self.isBackendHealthy() {
                    await MainActor.run {
                        self.state = .ready
                    }
                    return
                }
                try? await Task.sleep(nanoseconds: 500_000_000)
            }

            await MainActor.run {
                self.state = .failed("The backend did not become ready on 127.0.0.1:\(self.port).")
            }
        }
    }

    private func isBackendHealthy() async -> Bool {
        do {
            let healthURL = URL(string: "http://127.0.0.1:\(port)/api/health")!
            var request = URLRequest(url: healthURL)
            request.timeoutInterval = 1.0
            let (_, response) = try await URLSession.shared.data(for: request)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }

    private func cleanupProcessState() {
        process = nil
        try? logHandle?.close()
        logHandle = nil
    }

    private func resolveBackendLaunch() throws -> BackendLaunch {
        let environmentPath = ProcessInfo.processInfo.environment["MOXY_BACKEND_EXECUTABLE"]
        if let environmentPath, !environmentPath.isEmpty {
            return BackendLaunch(
                executableURL: URL(fileURLWithPath: environmentPath),
                arguments: [],
                currentDirectoryURL: nil,
                environment: backendEnvironment()
            )
        }

        if let resourceURL = Bundle.main.resourceURL {
            let helperURL = resourceURL
                .appendingPathComponent("Backend", isDirectory: true)
                .appendingPathComponent("MLX-Moxy-Wirks-Backend")
            if fileManager.isExecutableFile(atPath: helperURL.path) {
                return BackendLaunch(
                    executableURL: helperURL,
                    arguments: [],
                    currentDirectoryURL: helperURL.deletingLastPathComponent(),
                    environment: backendEnvironment()
                )
            }
        }

        let repoRoot = URL(fileURLWithPath: fileManager.currentDirectoryPath, isDirectory: true)
        let devEntry = repoRoot.appendingPathComponent("backend_entry.py")
        if fileManager.fileExists(atPath: devEntry.path) {
            return BackendLaunch(
                executableURL: URL(fileURLWithPath: "/usr/bin/env"),
                arguments: ["python3", devEntry.path],
                currentDirectoryURL: repoRoot,
                environment: backendEnvironment()
            )
        }

        throw BackendError.helperNotFound
    }

    private func backendEnvironment() -> [String: String] {
        var environment = ProcessInfo.processInfo.environment
        environment["MLX_MOXY_HOST"] = "127.0.0.1"
        environment["MLX_MOXY_OPEN_BROWSER"] = "0"
        environment["MLX_MOXY_AUTH_TOKEN"] = authToken
        return environment
    }
}

private struct BackendLaunch {
    let executableURL: URL
    let arguments: [String]
    let currentDirectoryURL: URL?
    let environment: [String: String]
}

private enum BackendError: LocalizedError {
    case helperNotFound

    var errorDescription: String? {
        switch self {
        case .helperNotFound:
            return "Could not find the bundled backend helper. Rebuild the macOS app bundle."
        }
    }
}
