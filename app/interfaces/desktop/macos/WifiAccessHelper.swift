import AppKit
import CoreLocation
import CoreWLAN
import Darwin
import Dispatch
import Foundation

private struct WifiAccessResponse: Encodable {
    let status: String
    let networkName: String?
    let message: String?

    enum CodingKeys: String, CodingKey {
        case status
        case networkName = "network_name"
        case message
    }
}

private func finish(
    status: String,
    networkName: String? = nil,
    message: String? = nil
) -> Never {
    let response = WifiAccessResponse(
        status: status,
        networkName: networkName,
        message: message
    )
    if let data = try? JSONEncoder().encode(response) {
        if let path = resultFilePath() {
            FileManager.default.createFile(
                atPath: path,
                contents: data,
                attributes: [.posixPermissions: 0o600]
            )
        } else {
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data([0x0a]))
        }
    }
    fflush(stdout)
    exit(0)
}

private func resultFilePath() -> String? {
    guard let index = CommandLine.arguments.firstIndex(of: "--result-file"),
          index + 1 < CommandLine.arguments.count else {
        return nil
    }
    let path = CommandLine.arguments[index + 1].trimmingCharacters(in: .whitespacesAndNewlines)
    return path.isEmpty ? nil : path
}

final class LocationAuthorizationController: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
    }

    func start() {
        guard CLLocationManager.locationServicesEnabled() else {
            finish(status: "location_services_disabled")
        }

        handleAuthorization(manager.authorizationStatus)
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        handleAuthorization(manager.authorizationStatus)
    }

    private func handleAuthorization(_ status: CLAuthorizationStatus) {
        switch status {
        case .authorizedAlways, .authorizedWhenInUse:
            readSSID()
        case .denied, .restricted:
            finish(status: "permission_denied")
        case .notDetermined:
            manager.requestWhenInUseAuthorization()
        @unknown default:
            finish(status: "permission_unknown")
        }
    }

    private func readSSID() {
        guard let interface = CWWiFiClient.shared().interface() else {
            finish(status: "ssid_unavailable")
        }
        guard let ssid = interface.ssid(), !ssid.isEmpty else {
            finish(status: "ssid_unavailable")
        }
        finish(status: "available", networkName: ssid)
    }
}

let application = NSApplication.shared
application.setActivationPolicy(.accessory)
application.activate(ignoringOtherApps: true)

let authorizationController = LocationAuthorizationController()
authorizationController.start()
DispatchQueue.main.asyncAfter(deadline: .now() + 30) {
    finish(status: "helper_timeout")
}
application.run()
