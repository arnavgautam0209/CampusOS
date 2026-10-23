import Foundation

struct Lab: Identifiable, Hashable {
    let id: String
    let name: String
    let location: String
    let symbol: String
    let capacity: Int
    let equipment: [String]
    let isOpenForBooking: Bool

    static let examples: [Lab] = [
        Lab(id: "robotics", name: "Robotics Lab", location: "Block A · Room 204",
            symbol: "cpu", capacity: 30,
            equipment: ["Arduino", "ESP32", "Motors", "Soldering stations"], isOpenForBooking: true),
        Lab(id: "electronics", name: "Electronics Lab", location: "Block B · Room 102",
            symbol: "bolt", capacity: 40,
            equipment: ["Oscilloscopes", "Multimeters", "Power supplies"], isOpenForBooking: true),
        Lab(id: "printing", name: "3D Printing Lab", location: "Innovation Centre",
            symbol: "printer", capacity: 15,
            equipment: ["3D printers", "CAD computers", "Filament"], isOpenForBooking: false),
        Lab(id: "computing", name: "AI Computing Lab", location: "Block C · Room 301",
            symbol: "desktopcomputer", capacity: 50,
            equipment: ["GPU computers", "Development kits"], isOpenForBooking: true)
    ]
}
