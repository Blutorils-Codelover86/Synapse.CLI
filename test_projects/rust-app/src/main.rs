use std::path::Path;

struct ImageProcessor {
    width: u32,
    height: u32,
}

impl ImageProcessor {
    fn new(width: u32, height: u32) -> Self {
        Self { width, height }
    }

    fn resize(&self, scale: f32) -> (u32, u32) {
        let new_w = (self.width as f32 * scale) as u32;
        let new_h = (self.height as f32 * scale) as u32;
        (new_w, new_h)
    }
}

fn main() {
    let processor = ImageProcessor::new(1920, 1080);
    let (w, h) = processor.resize(0.5);
    println!("Resized: {}x{}", w, h);
}
