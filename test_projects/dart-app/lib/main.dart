import 'package:flutter/material.dart';
import 'package:camera/camera.dart';

class CameraManager {
  CameraController? _controller;
  List<CameraDescription> _cameras = [];

  Future<void> initialize() async {
    _cameras = await availableCameras();
    if (_cameras.isNotEmpty) {
      _controller = CameraController(_cameras[0], ResolutionPreset.high);
      await _controller!.initialize();
    }
  }

  Future<void> captureFrame() async {
    if (_controller != null && _controller!.value.isInitialized) {
      await _controller!.takePicture();
    }
  }

  void dispose() {
    _controller?.dispose();
  }
}

Future<void> initializeCamera() async {
  final manager = CameraManager();
  await manager.initialize();
}

class CameraApp extends StatelessWidget {
  const CameraApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: Scaffold(
        appBar: AppBar(title: const Text('Camera')),
        body: const Center(child: Text('Camera Preview')),
      ),
    );
  }
}
