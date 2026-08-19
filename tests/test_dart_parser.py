"""Tests for the Dart parser."""

import pytest
from synapse.parser.dart_parser import DartParser
from synapse.parser.base import SymbolType


@pytest.fixture
def parser():
    return DartParser()


class TestDartParser:
    def test_imports(self, parser):
        source = """
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
"""
        result = parser.parse(source)
        assert len(result.imports) == 2
        modules = [i.module_name for i in result.imports]
        assert any("flutter" in m for m in modules)
        assert any("camera" in m for m in modules)

    def test_class_extraction(self, parser):
        source = """
class CameraManager {
  CameraController? _controller;

  Future<void> initialize() async {
    _controller = await availableCameras();
  }

  Future<void> captureFrame() async {
    await _controller?.takePicture();
  }

  void dispose() {
    _controller?.dispose();
  }
}
"""
        result = parser.parse(source)
        classes = [s for s in result.symbols if s.symbol_type == SymbolType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "CameraManager"

        methods = [s for s in result.symbols if s.symbol_type == SymbolType.METHOD]
        assert len(methods) == 3
        method_names = [m.name for m in methods]
        assert "initialize" in method_names
        assert "captureFrame" in method_names
        assert "dispose" in method_names

    def test_standalone_function(self, parser):
        source = """
Future<void> initializeCamera() async {
  final manager = CameraManager();
  await manager.initialize();
}
"""
        result = parser.parse(source)
        functions = [s for s in result.symbols if s.symbol_type == SymbolType.FUNCTION]
        assert len(functions) == 1
        assert functions[0].name == "initializeCamera"

    def test_class_with_extends(self, parser):
        source = """
class CameraApp extends StatelessWidget {
  const CameraApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp();
  }
}
"""
        result = parser.parse(source)
        classes = [s for s in result.symbols if s.symbol_type == SymbolType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "CameraApp"

        methods = [s for s in result.symbols if s.symbol_type == SymbolType.METHOD]
        assert len(methods) >= 1

    def test_enum(self, parser):
        source = """
enum CameraMode {
  photo,
  video,
  portrait,
}
"""
        result = parser.parse(source)
        enums = [s for s in result.symbols if s.symbol_type == SymbolType.ENUM]
        assert len(enums) == 1
        assert enums[0].name == "CameraMode"

    def test_invalid_dart(self, parser):
        source = """
class broken(
    this is not valid dart
    @@@
"""
        result = parser.parse(source)
        assert isinstance(result.errors, list)

    def test_empty_file(self, parser):
        result = parser.parse("")
        assert len(result.symbols) == 0
        assert len(result.imports) == 0

    def test_relative_import(self, parser):
        source = "import './utils.dart';\n"
        result = parser.parse(source)
        assert len(result.imports) == 1
        assert result.imports[0].is_relative is True

    def test_export_import(self, parser):
        source = "export 'src/camera.dart';\n"
        result = parser.parse(source)
        assert len(result.imports) == 1
        assert result.imports[0].metadata.get("is_export") is True
