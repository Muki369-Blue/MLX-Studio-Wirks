// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "MLXMoxyWirksMac",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "MLX-Moxy-Wirks", targets: ["MLXMoxyWirks"])
    ],
    targets: [
        .executableTarget(
            name: "MLXMoxyWirks",
            path: "Sources/MLXMoxyWirks"
        )
    ]
)
