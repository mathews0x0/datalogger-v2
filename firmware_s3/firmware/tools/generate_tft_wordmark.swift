import AppKit
import Foundation

let width = 320
let height = 240
let outPNG = URL(fileURLWithPath: "docs/assets/racesense-wordmark-final.png")
let outRAW = URL(fileURLWithPath: "firmware/lib/tft_wordmark.raw")

try FileManager.default.createDirectory(
    at: outPNG.deletingLastPathComponent(),
    withIntermediateDirectories: true
)

let bg = NSColor.black
let white = NSColor.white
let orange = NSColor(calibratedRed: 244.0 / 255.0, green: 123.0 / 255.0, blue: 32.0 / 255.0, alpha: 1.0)

func font(_ size: CGFloat) -> NSFont {
    return NSFont(name: "Arial-BoldItalicMT", size: size)
        ?? NSFont(name: "Arial-BoldItalic", size: size)
        ?? NSFont.boldSystemFont(ofSize: size)
}

func textSize(_ text: String, _ font: NSFont) -> NSSize {
    return (text as NSString).size(withAttributes: [.font: font])
}

func drawText(_ text: String, x: CGFloat, y: CGFloat, size: CGFloat, color: NSColor) {
    let attrs: [NSAttributedString.Key: Any] = [
        .font: font(size),
        .foregroundColor: color
    ]
    (text as NSString).draw(at: NSPoint(x: x, y: y), withAttributes: attrs)
}

let image = NSImage(size: NSSize(width: width, height: height))
image.lockFocus()
bg.setFill()
NSBezierPath(rect: NSRect(x: 0, y: 0, width: width, height: height)).fill()

orange.setFill()
NSBezierPath(rect: NSRect(x: 0, y: height - 3, width: width, height: 3)).fill()
NSBezierPath(rect: NSRect(x: 0, y: 0, width: width, height: 3)).fill()

let bigSize: CGFloat = 62
let smallSize: CGFloat = 44
let fBig = font(bigSize)
let fSmall = font(smallSize)
let segments: [(String, CGFloat, NSFont)] = [
    ("R", bigSize, fBig),
    ("ACE", smallSize, fSmall),
    ("S", bigSize, fBig),
    ("ENSE", smallSize, fSmall),
]

let tracking: CGFloat = -4
let sizes = segments.map { textSize($0.0, $0.2) }
let totalWidth = sizes.reduce(CGFloat(0)) { $0 + $1.width } + tracking * CGFloat(segments.count - 1)
var x = (CGFloat(width) - totalWidth) / 2.0
let bigY: CGFloat = 100
let smallY: CGFloat = 104

for pass in 0..<2 {
    x = (CGFloat(width) - totalWidth) / 2.0
    for idx in 0..<segments.count {
        let seg = segments[idx]
        let isBig = seg.0 == "R" || seg.0 == "S"
        let y = isBig ? bigY : smallY
        if pass == 0 {
            drawText(seg.0, x: x + 4, y: y - 4, size: seg.1, color: orange)
        } else {
            drawText(seg.0, x: x, y: y, size: seg.1, color: white)
        }
        x += sizes[idx].width + tracking
    }
}

orange.setFill()
NSBezierPath(rect: NSRect(x: 68, y: 83, width: 184, height: 4)).fill()
image.unlockFocus()

guard let tiff = image.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff),
      let png = bitmap.representation(using: .png, properties: [:]) else {
    fatalError("Failed to create PNG")
}
try png.write(to: outPNG)

var raw = Data(capacity: width * height * 2)
for yy in 0..<height {
    for xx in 0..<width {
        let c = bitmap.colorAt(x: xx, y: yy) ?? bg
        let r = Int(c.redComponent * 255.0)
        let g = Int(c.greenComponent * 255.0)
        let b = Int(c.blueComponent * 255.0)
        let rgb565 = UInt16(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3))
        raw.append(UInt8((rgb565 >> 8) & 0xFF))
        raw.append(UInt8(rgb565 & 0xFF))
    }
}
try raw.write(to: outRAW)
print("Wrote \(outPNG.path)")
print("Wrote \(outRAW.path)")
