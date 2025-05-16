# utils/image_utils.py
from PIL import Image, UnidentifiedImageError, ExifTags
import io
import logging
import os

# Khởi tạo logger
logger = logging.getLogger(__name__)

def _preserve_orientation(image):
    """
    Checks for EXIF orientation data and rotates the image accordingly.
    Returns the potentially rotated image.
    """
    try:
        # Tìm tag orientation trong EXIF data
        for orientation_tag in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation_tag] == 'Orientation':
                break
        
        exif = image._getexif() # Lấy EXIF data (nếu có)
        if exif is not None:
            orientation = exif.get(orientation_tag)
            logger.debug(f"Original image orientation from EXIF: {orientation}")

            if orientation == 3:
                image = image.rotate(180, expand=True)
                logger.info("Image rotated 180 degrees based on EXIF orientation.")
            elif orientation == 6:
                image = image.rotate(270, expand=True)
                logger.info("Image rotated 270 degrees (CW) based on EXIF orientation.")
            elif orientation == 8:
                image = image.rotate(90, expand=True)
                logger.info("Image rotated 90 degrees (CW) based on EXIF orientation.")
            # Các trường hợp khác (1, 2, 4, 5, 7) có thể liên quan đến lật ảnh (flip)
            # Hiện tại chúng ta chỉ xử lý các trường hợp xoay phổ biến.
            # Orientation 1 là bình thường, không cần làm gì.
    except (AttributeError, KeyError, IndexError, TypeError):
        # Lỗi khi đọc EXIF data hoặc tag không tồn tại
        logger.warning("Could not read or apply EXIF orientation data.", exc_info=False) # exc_info=False để không log traceback
    return image


def resize_image(
    image_path_or_binary,
    output_path=None,
    width=None,
    height=None,
    output_format='JPEG',
    quality=85,
    only_if_larger=True,
    preserve_aspect_ratio=True
):
    """
    Resizes an image using Pillow.
    Can take an image path or binary data as input.
    If output_path is None, returns the resized image as binary data in memory.

    :param image_path_or_binary: Path to the image file or binary image data (bytes).
    :param output_path: Path to save the resized image. If None, returns binary data.
    :param width: Desired width. If None and height is provided, scales by height.
    :param height: Desired height. If None and width is provided, scales by width.
                   If both are None, no resize happens but format conversion can still occur.
    :param output_format: Desired output format (e.g., 'JPEG', 'PNG', 'WEBP').
    :param quality: Quality for JPEG/WEBP (1-95 for JPEG, 1-100 for WEBP).
    :param only_if_larger: If True, only resizes if the original image is larger than target dimensions.
    :param preserve_aspect_ratio: If True, maintains aspect ratio. If False and both width/height
                                  are given, it will crop/stretch (Pillow's thumbnail crops by default).
                                  For this function, if False and both width/height given, it will resize
                                  to exact dimensions, potentially changing aspect ratio.
    :return: Path to the saved image if output_path is provided,
             otherwise binary data of the resized image (bytes). Returns None on error.
    """
    try:
        if isinstance(image_path_or_binary, str):
            if not os.path.exists(image_path_or_binary):
                logger.error(f"Image file not found at: {image_path_or_binary}")
                return None
            img = Image.open(image_path_or_binary)
            logger.info(f"Opened image from path: {image_path_or_binary}")
        elif isinstance(image_path_or_binary, bytes):
            img = Image.open(io.BytesIO(image_path_or_binary))
            logger.info("Opened image from binary data.")
        else:
            logger.error("Invalid image input type. Must be path (str) or binary (bytes).")
            return None

        # Giữ nguyên định dạng nếu có thể và cần thiết (ví dụ ảnh động GIF)
        # Pillow không giữ animation khi resize và save sang format khác.
        # Nếu muốn giữ GIF động, cần xử lý đặc biệt hoặc không resize.
        if img.format == "GIF" and output_format.upper() == "GIF":
            # Nếu không resize và chỉ muốn đổi tên/lưu, thì không cần Pillow xử lý nhiều
            # Tuy nhiên, hàm này chủ yếu để resize.
            # Hiện tại, nếu là GIF và không resize, nó sẽ được lưu lại (có thể mất animation nếu có xử lý)
            logger.warning("GIF resizing might result in static image. Animation may be lost unless handled specifically.")


        # Xử lý xoay ảnh theo EXIF
        img = _preserve_orientation(img)

        original_width, original_height = img.size
        logger.debug(f"Original image dimensions: {original_width}x{original_height}, Format: {img.format}")

        # Xác định kích thước mới
        target_w, target_h = width, height

        if not target_w and not target_h:
            logger.info("No target width or height specified. Skipping resize, will only convert format if needed.")
            # Vẫn xử lý convert format và save/return binary
        elif only_if_larger and (original_width <= (target_w or original_width) and original_height <= (target_h or original_height)):
            logger.info("Image is not larger than target dimensions and only_if_larger is True. Skipping resize.")
            # Vẫn xử lý convert format và save/return binary
        else:
            if preserve_aspect_ratio:
                if target_w and target_h: # Cả width và height đều được cung cấp
                    # Giữ aspect ratio, thu nhỏ để vừa cả width và height (thumbnail behavior)
                    img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
                    logger.info(f"Resized image (preserving aspect ratio to fit within {target_w}x{target_h}) to: {img.size[0]}x{img.size[1]}")
                elif target_w: # Chỉ có width
                    aspect_ratio = original_height / original_width
                    new_height = int(target_w * aspect_ratio)
                    img = img.resize((target_w, new_height), Image.Resampling.LANCZOS)
                    logger.info(f"Resized image (preserving aspect ratio by width {target_w}) to: {img.size[0]}x{img.size[1]}")
                elif target_h: # Chỉ có height
                    aspect_ratio = original_width / original_height
                    new_width = int(target_h * aspect_ratio)
                    img = img.resize((new_width, target_h), Image.Resampling.LANCZOS)
                    logger.info(f"Resized image (preserving aspect ratio by height {target_h}) to: {img.size[0]}x{img.size[1]}")
            else: # Không giữ aspect ratio (nếu cả width và height được cung cấp)
                if target_w and target_h:
                    img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                    logger.info(f"Resized image (exact dimensions, aspect ratio may change) to: {target_w}x{target_h}")
                else:
                    # Nếu chỉ có width hoặc height và preserve_aspect_ratio=False, hành vi giống True
                    logger.warning("preserve_aspect_ratio is False, but only one dimension (width or height) was provided. Aspect ratio will be preserved based on that dimension.")
                    # Logic tương tự như preserve_aspect_ratio=True trong trường hợp này
                    if target_w:
                        aspect_ratio = original_height / original_width
                        new_height = int(target_w * aspect_ratio)
                        img = img.resize((target_w, new_height), Image.Resampling.LANCZOS)
                    elif target_h:
                        aspect_ratio = original_width / original_height
                        new_width = int(target_h * aspect_ratio)
                        img = img.resize((new_width, target_h), Image.Resampling.LANCZOS)


        # Chuyển đổi sang RGB nếu là ảnh RGBA (có kênh alpha) để lưu JPEG/WEBP không lỗi
        # Trừ khi output là PNG hoặc GIF có thể giữ alpha
        if output_format.upper() in ['JPEG', 'JPG', 'WEBP'] and img.mode in ('RGBA', 'P'): # 'P' là palette-based
            logger.debug(f"Image mode is {img.mode}. Converting to RGB for {output_format} output.")
            img = img.convert("RGB")

        # Lưu hoặc trả về binary
        if output_path:
            # Tạo thư mục nếu chưa tồn tại
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            save_params = {}
            if output_format.upper() in ['JPEG', 'JPG']:
                save_params['quality'] = quality
                save_params['optimize'] = True # Cố gắng tối ưu hóa
                save_params['progressive'] = True # Tạo JPEG progressive
            elif output_format.upper() == 'PNG':
                save_params['optimize'] = True
            elif output_format.upper() == 'WEBP':
                save_params['quality'] = quality
                # save_params['lossless'] = False # Mặc định là lossy
            
            img.save(output_path, format=output_format, **save_params)
            logger.info(f"Resized image saved to: {output_path} (Format: {output_format}, Quality: {quality if output_format.upper() in ['JPEG', 'WEBP'] else 'N/A'})")
            return output_path
        else:
            img_byte_arr = io.BytesIO()
            save_params_in_memory = {}
            if output_format.upper() in ['JPEG', 'JPG']:
                save_params_in_memory['quality'] = quality
            elif output_format.upper() == 'WEBP':
                 save_params_in_memory['quality'] = quality

            img.save(img_byte_arr, format=output_format, **save_params_in_memory)
            img_byte_arr = img_byte_arr.getvalue()
            logger.info(f"Resized image returned as binary data (Format: {output_format}, Size: {len(img_byte_arr)} bytes).")
            return img_byte_arr

    except UnidentifiedImageError:
        logger.error(f"Cannot identify image file. It might be corrupted or not a valid image: {str(image_path_or_binary)[:100]}")
        return None
    except FileNotFoundError: # Chỉ xảy ra nếu input là path và đã qua check os.path.exists
        logger.error(f"Image file not found (should have been caught earlier): {image_path_or_binary}")
        return None
    except Exception as e:
        logger.error(f"Error resizing image '{str(image_path_or_binary)[:100]}...': {e}", exc_info=True) # exc_info=True để log traceback
        return None

# --- Example Usage ---
# if __name__ == "__main__":
#     # from utils.logging_config import setup_logging
#     # setup_logging(log_level_str="DEBUG") # Đặt DEBUG để thấy log chi tiết hơn
#
#     # --- Test với file ---
#     # Tạo một file ảnh dummy (ví dụ placeholder.png) để test
#     # Hoặc dùng một ảnh có sẵn trên máy bạn
#     # dummy_image_path = "placeholder.png"
#     # try:
#     #     Image.new('RGB', (1200, 900), color = 'red').save(dummy_image_path)
#     #     logger.info(f"Created dummy image at {dummy_image_path}")
#     # except Exception as e:
#     #     logger.error(f"Could not create dummy image: {e}")
#
#     # if os.path.exists(dummy_image_path):
#     #     # Resize và lưu file
#     #     resized_file_path = resize_image(
#     #         dummy_image_path,
#     #         output_path="resized_placeholder.jpg",
#     #         width=600,
#     #         # height=400, # Để trống height để giữ aspect ratio theo width
#     #         output_format='JPEG',
#     #         quality=80
#     #     )
#     #     if resized_file_path:
#     #         logger.info(f"Test 1: Resized file saved to {resized_file_path}")
#
#     #     # Resize và trả về binary
#     #     image_binary = resize_image(
#     #         dummy_image_path,
#     #         width=300,
#     #         output_format='PNG'
#     #     )
#     #     if image_binary:
#     #         logger.info(f"Test 2: Resized image binary received (length: {len(image_binary)} bytes).")
#     #         # Có thể lưu binary này vào file để kiểm tra
#     #         with open("resized_from_binary.png", "wb") as f:
#     #             f.write(image_binary)
#     #         logger.info("Saved binary to resized_from_binary.png for verification.")
#
#     #     # Test only_if_larger
#     #     small_target_path = resize_image(
#     #         dummy_image_path,
#     #         output_path="small_target_test.jpg",
#     #         width=1500, # Lớn hơn ảnh gốc
#     #         only_if_larger=True
#     #     ) # Ảnh sẽ không được resize, chỉ đổi format và lưu
#     #     if small_target_path:
#     #         logger.info(f"Test 3 (only_if_larger=True, target larger): Image saved at {small_target_path}")
#
#     #     os.remove(dummy_image_path) # Xóa file dummy
#     # else:
#     #     logger.error(f"Dummy image {dummy_image_path} not found for testing.")
#
#     # --- Test với binary data (ví dụ lấy từ HTTP request) ---
#     # import requests
#     # try:
#     #     response = requests.get("https://via.placeholder.com/1000x800.png?text=Test+Image+From+URL", stream=True)
#     #     response.raise_for_status()
#     #     image_bytes_from_url = response.content
#     #     logger.info("Successfully downloaded image from URL for binary test.")
#
#     #     resized_binary_from_url = resize_image(
#     #         image_bytes_from_url,
#     #         width=500,
#     #         output_format='JPEG',
#     #         quality=75
#     #     )
#     #     if resized_binary_from_url:
#     #         with open("resized_from_url_binary.jpg", "wb") as f:
#     #             f.write(resized_binary_from_url)
#     #         logger.info("Saved image from URL binary to resized_from_url_binary.jpg")
#
#     # except requests.exceptions.RequestException as e:
#     #     logger.error(f"Could not download image for binary test: {e}")