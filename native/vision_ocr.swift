import Foundation
import Vision
import ImageIO

// Vision uses a lower-left origin. The browser canvas uses top-left coordinates.
guard CommandLine.arguments.count == 2 else { exit(2) }
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "en-US", "zh-Hant"]
request.automaticallyDetectsLanguage = true
request.usesLanguageCorrection = false
try VNImageRequestHandler(url: url).perform([request])
let lines: [[String: Any]] = (request.results ?? []).compactMap { observation in
    guard let text = observation.topCandidates(1).first?.string else { return nil }
    let box = observation.boundingBox
    return ["original": text, "box": [box.minX, 1 - box.maxY, box.width, box.height]]
}
FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: lines))
