import Cocoa

let size = NSSize(width: 1024, height: 1024)
let image = NSImage(size: size)
image.lockFocus()

let background = NSBezierPath(roundedRect: NSRect(x: 52, y: 52, width: 920, height: 920), xRadius: 210, yRadius: 210)
NSColor(calibratedRed: 0.086, green: 0.459, blue: 0.290, alpha: 1).setFill()
background.fill()

let pulse = NSBezierPath()
pulse.move(to: NSPoint(x: 165, y: 510))
pulse.line(to: NSPoint(x: 335, y: 510))
pulse.line(to: NSPoint(x: 405, y: 685))
pulse.line(to: NSPoint(x: 505, y: 325))
pulse.line(to: NSPoint(x: 595, y: 590))
pulse.line(to: NSPoint(x: 665, y: 510))
pulse.line(to: NSPoint(x: 859, y: 510))
pulse.lineWidth = 52
pulse.lineJoinStyle = .round
pulse.lineCapStyle = .round
NSColor.white.setStroke()
pulse.stroke()

image.unlockFocus()
guard let tiff = image.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff),
      let png = bitmap.representation(using: .png, properties: [:]) else { exit(1) }
try png.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
