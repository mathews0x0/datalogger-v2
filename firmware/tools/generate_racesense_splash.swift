import AppKit
import Foundation

// Regenerate the P4 boot logo after changing the server-side brand asset.
// Run from the repository root:
//   swift firmware/tools/generate_racesense_splash.swift

let inputURL = URL(fileURLWithPath: "server/ui/assets/RS full logo.png")
let outputURL = URL(fileURLWithPath: "firmware/components/ui/assets/racesense_splash_rgb565.bin")
let previewURL = URL(fileURLWithPath: "docs/assets/racesense-splash-800x480.png")

let panelWidth = 640
let panelHeight = 230
let screenWidth = 800
let screenHeight = 480
let background = NSColor(calibratedRed: 5.0 / 255.0,
                         green: 5.0 / 255.0,
                         blue: 8.0 / 255.0,
                         alpha: 1.0)
let orange = NSColor(calibratedRed: 255.0 / 255.0,
                     green: 107.0 / 255.0,
                     blue: 53.0 / 255.0,
                     alpha: 1.0)
let muted = NSColor(calibratedRed: 154.0 / 255.0,
                    green: 154.0 / 255.0,
                    blue: 166.0 / 255.0,
                    alpha: 1.0)

guard let source = NSImage(contentsOf: inputURL) else {
    fatalError("Unable to load server logo at \(inputURL.path)")
}

func makeImage(width: Int, height: Int, draw: (NSImage) -> Void) -> NSBitmapImageRep {
    let image = NSImage(size: NSSize(width: width, height: height))
    image.lockFocus()
    draw(image)
    image.unlockFocus()
    guard let tiff = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff) else {
        fatalError("Unable to rasterize splash image")
    }
    return bitmap
}

func fill(_ color: NSColor, _ rect: NSRect) {
    color.setFill()
    NSBezierPath(rect: rect).fill()
}

func drawLogo(_ image: NSImage, in rect: NSRect) {
    image.draw(in: rect,
               from: NSRect(origin: .zero, size: image.size),
               // The web page uses mix-blend-mode: screen for this asset. The
               // same blend keeps the logo's black canvas from becoming a
               // visible rectangle on the device splash.
               operation: .screen,
               fraction: 1.0,
               respectFlipped: true,
               hints: [.interpolation: NSImageInterpolation.high])
    NSGraphicsContext.current?.compositingOperation = .sourceOver
}

let logoRect = NSRect(x: 20, y: 4, width: 600, height: 223)
let logoPanel = makeImage(width: panelWidth, height: panelHeight) { _ in
    fill(background, NSRect(x: 0, y: 0, width: panelWidth, height: panelHeight))
    drawLogo(source, in: logoRect)
}

try FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(),
                                         withIntermediateDirectories: true)
try FileManager.default.createDirectory(at: previewURL.deletingLastPathComponent(),
                                         withIntermediateDirectories: true)

var raw = Data(capacity: panelWidth * panelHeight * 2)
for y in 0..<panelHeight {
    for x in 0..<panelWidth {
        let color = logoPanel.colorAt(x: x, y: y) ?? background
        let red = Int(color.redComponent * 255.0)
        let green = Int(color.greenComponent * 255.0)
        let blue = Int(color.blueComponent * 255.0)
        let rgb565 = UInt16(((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3))
        // LVGL reads this as an ESP32-native lv_color_t (little endian).
        raw.append(UInt8(rgb565 & 0xFF))
        raw.append(UInt8((rgb565 >> 8) & 0xFF))
    }
}
try raw.write(to: outputURL)

let preview = makeImage(width: screenWidth, height: screenHeight) { _ in
    fill(background, NSRect(x: 0, y: 0, width: screenWidth, height: screenHeight))
    fill(orange, NSRect(x: 48, y: 428, width: 704, height: 2))
    drawLogo(source, in: NSRect(x: 80, y: 176, width: 640, height: 238))

    fill(NSColor(calibratedWhite: 0.16, alpha: 1.0), NSRect(x: 180, y: 94, width: 440, height: 8))
    fill(orange, NSRect(x: 180, y: 94, width: 308, height: 8))

    let detailAttributes: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: 15, weight: .medium),
        .foregroundColor: muted,
        .kern: 1.0,
    ]
    ("PREPARING TELEMETRY ENGINE" as NSString).draw(at: NSPoint(x: 280, y: 57),
                                                     withAttributes: detailAttributes)

    let tagAttributes: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: 11, weight: .semibold),
        .foregroundColor: orange,
        .kern: 2.0,
    ]
    ("RIDE FASTER  /  RIDE SMARTER" as NSString).draw(at: NSPoint(x: 297, y: 33),
                                                       withAttributes: tagAttributes)
}
guard let png = preview.representation(using: .png, properties: [:]) else {
    fatalError("Unable to encode splash preview")
}
try png.write(to: previewURL)

print("Wrote \(outputURL.path) (\(raw.count) bytes)")
print("Wrote \(previewURL.path)")
