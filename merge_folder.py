
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path

# ========== تنظیمات ==========
# پوشه‌هایی که باید نادیده گرفته شوند (نام دقیق)
EXCLUDED_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".cache",
    "__pycache__",
    "coverage",
    ".next",
    "out",
    ".vscode",
    ".idea",
    ".venv"
}

# پسوندهای باینری (این فایل‌ها وارد نمی‌شوند)
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".bmp",
    ".mp4",
    ".mp3",
    ".wav",
    ".ogg",
    ".flac",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".obj",
    ".o",
    ".tsbuildinfo",  # فایل اطلاعات بیلد TypeScript
    ".psd",
    ".ai",
    ".ttf",
    ".woff",
    ".woff2",
    ".eot",
    ".otf",
}

# نام فایل خروجی (نادیده گرفته می‌شود)
OUTPUT_FILE = "merged_codes.txt"


def should_include_file(file_path: Path, root_dir: Path) -> bool:
    """
    بررسی می‌کند که آیا یک فایل باید در خروجی قرار گیرد یا خیر.
    """
    rel_path = file_path.relative_to(root_dir).as_posix()
    # نادیده گرفتن فایل خروجی
    if rel_path == OUTPUT_FILE:
        return False

    # بررسی پسوند باینری
    ext = file_path.suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return False

    # بررسی محتوای فایل برای اطمینان از متنی بودن (اختیاری)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            f.read(1024)  # خواندن چند بایت اول برای تست
    except (UnicodeDecodeError, IOError):
        return False

    return True


def should_skip_dir(dir_path: Path) -> bool:
    """
    بررسی می‌کند که آیا یک دایرکتوری باید اسکیپ شود.
    """
    return dir_path.name in EXCLUDED_DIRS


def merge_folder(root_dir: Path, output_file: Path):
    """
    اصلی ترین تابع: تمام فایل‌های مجاز را پیدا کرده و در فایل خروجی می‌ریزد.
    """
    # جمع‌آوری مسیر تمام فایل‌های مجاز (به صورت مرتب شده)
    all_files = []
    for current_dir, subdirs, files in os.walk(root_dir):
        # حذف دایرکتوری‌های ناخواسته از لیست پیمایش (برای عملکرد بهتر)
        subdirs[:] = [d for d in subdirs if not should_skip_dir(Path(current_dir) / d)]

        for file in files:
            file_path = Path(current_dir) / file
            if should_include_file(file_path, root_dir):
                all_files.append(file_path)

    # مرتب‌سازی بر اساس مسیر نسبی
    all_files.sort()

    # نوشتن در فایل خروجی
    with open(output_file, "w", encoding="utf-8") as out_f:
        for file_path in all_files:
            rel_path = file_path.relative_to(root_dir).as_posix()
            # نوشتن هدر فایل
            out_f.write(f"\n{'=' * 80}\n")
            out_f.write(f"# فایل: {rel_path}\n")
            out_f.write(f"{'=' * 80}\n\n")

            # نوشتن محتوای فایل
            try:
                with open(file_path, "r", encoding="utf-8") as in_f:
                    out_f.write(in_f.read())
                out_f.write("\n\n")  # فاصله بین فایل‌ها
            except Exception as e:
                out_f.write(f"!! خطا در خواندن فایل: {e}\n\n")

    print(
        f"✅ ادغام کامل شد! تعداد {len(all_files)} فایل در '{output_file}' ذخیره شدند."
    )


if __name__ == "__main__":
    # تشخیص پوشه مورد نظر (آرگومان خط فرمان یا پوشه جاری)
    if len(sys.argv) > 1:
        target_dir = Path(sys.argv[1]).resolve()
    else:
        target_dir = Path.cwd()

    if not target_dir.is_dir():
        print(f"❌ خطا: '{target_dir}' یک پوشه معتبر نیست.")
        sys.exit(1)

    output_path = target_dir / OUTPUT_FILE
    print(f"🔍 شروع اسکن پوشه: {target_dir}")
    print(f"📄 فایل خروجی: {output_path}")
    merge_folder(target_dir, output_path)







