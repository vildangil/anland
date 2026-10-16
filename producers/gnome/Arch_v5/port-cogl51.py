#!/usr/bin/env python3
"""Rework AnLand's DMA-BUF framebuffer import for CoglRendererEGL in Mutter 51.

Only changes the function inserted by the AnLand patch, after the reviewed
three-way merge. The build must still verify C types and runtime semantics.
"""
from pathlib import Path
import sys

tree = Path(sys.argv[1])
source = tree / "src/backends/native/meta-renderer-native.c"
content = source.read_text()

start_token = "CoglFramebuffer *\nmeta_renderer_native_create_dma_buf_framebuffer ("
end_token = "\nstatic void\nconfigure_disabled_crtcs"
if content.count(start_token) != 1:
    raise RuntimeError("Expected exactly one AnLand dma-buf import function")
start = content.index(start_token)
end = content.index(end_token, start)

replacement = """CoglFramebuffer *
meta_renderer_native_create_dma_buf_framebuffer (MetaRendererNative  *renderer_native,
                                                 uint32_t             width,
                                                 uint32_t             height,
                                                 uint32_t             drm_format,
                                                 int                  n_planes,
                                                 int                 *fds,
                                                 uint32_t            *strides,
                                                 uint32_t            *offsets,
                                                 uint64_t            *modifiers,
                                                 GError             **error)
{
  CoglContext *cogl_context;
  CoglDisplay *cogl_display;
  CoglRenderer *cogl_renderer;
  CoglRendererEGL *renderer_egl;
  EGLImageKHR egl_image;
  CoglPixelFormat cogl_format;
  CoglTexture *cogl_tex;
  CoglOffscreen *cogl_fbo;
  const MetaFormatInfo *format_info;
  const uint64_t *import_modifiers = modifiers;

  cogl_context = meta_renderer_native_get_cogl_context (renderer_native);
  if (!cogl_context)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                           "No Cogl context for AnLand dma-buf import");
      return NULL;
    }

  cogl_display = cogl_context_get_display (cogl_context);
  cogl_renderer = cogl_display_get_renderer (cogl_display);
  if (!COGL_IS_RENDERER_EGL (cogl_renderer))
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED,
                           "The Cogl renderer does not support EGL image import");
      return NULL;
    }

  renderer_egl = COGL_RENDERER_EGL (cogl_renderer);
  format_info = meta_format_info_from_drm_format (drm_format);
  if (!format_info)
    {
      g_set_error (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED,
                   "Unsupported dma-buf format 0x%08x", drm_format);
      return NULL;
    }
  cogl_format = format_info->cogl_format;

  if (!cogl_renderer_egl_has_extensions (renderer_egl, NULL,
                                         "EGL_EXT_image_dma_buf_import", NULL))
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED,
                           "EGL does not support dma-buf image import");
      return NULL;
    }

  if (modifiers &&
      !cogl_renderer_egl_has_extensions (
        renderer_egl, NULL, "EGL_EXT_image_dma_buf_import_modifiers", NULL))
    {
      for (int i = 0; i < n_planes; i++)
        {
          if (modifiers[i] != DRM_FORMAT_MOD_LINEAR)
            {
              g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED,
                                   "EGL cannot import non-linear dma-buf modifiers");
              return NULL;
            }
        }
      import_modifiers = NULL;
    }

  egl_image = cogl_renderer_egl_create_dmabuf_image (renderer_egl,
                                                     width, height,
                                                     drm_format, n_planes,
                                                     fds, strides, offsets,
                                                     import_modifiers, error);
  if (egl_image == EGL_NO_IMAGE_KHR)
    return NULL;

  cogl_tex = cogl_texture_2d_new_from_egl_image (
    cogl_context, width, height, cogl_format, egl_image,
    COGL_EGL_IMAGE_FLAG_NO_GET_DATA, error);

  cogl_renderer_egl_destroy_image (renderer_egl, egl_image, NULL);
  if (!cogl_tex)
    return NULL;

  cogl_fbo = cogl_offscreen_new_with_texture (cogl_tex);
  g_object_unref (cogl_tex);

  if (!cogl_framebuffer_allocate (COGL_FRAMEBUFFER (cogl_fbo), error))
    {
      g_object_unref (cogl_fbo);
      return NULL;
    }

  return COGL_FRAMEBUFFER (cogl_fbo);
}
"""

updated = content[:start] + replacement + content[end:]
source.write_text(updated)
print("Ported AnLand DMA-BUF EGLImage framebuffer import to Mutter 51 CoglRendererEGL APIs")
