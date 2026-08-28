"""
Image to Excel Exporter
Embed product images directly in Excel files
"""

import logging
from typing import List, Dict
from pathlib import Path
import requests
from io import BytesIO
import tempfile

log = logging.getLogger('siar.image_excel_exporter')

class ImageExcelExporter:
    """Export products with embedded images to Excel"""

    def __init__(self):
        self.session = requests.Session()
        log.info("ImageExcelExporter initialized")

    def export_with_images(self, products: List[Dict], output_path: str = None) -> str:
        """
        Export products with embedded images to Excel

        Args:
            products: List of product dictionaries with image URLs
            output_path: Optional output file path

        Returns:
            Path to generated Excel file
        """
        try:
            import openpyxl
            from openpyxl.drawing.image import Image as XLImage
            from openpyxl.utils import get_column_letter
        except ImportError:
            log.error("openpyxl not installed")
            raise

        log.info(f"Exporting {len(products)} products with images")

        # Create workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Products"

        # Headers
        headers = ['Product', 'SKU', 'Price', 'Image', 'Description', 'URL']
        ws.append(headers)

        # Style header row
        for cell in ws[1]:
            cell.font = openpyxl.styles.Font(bold=True)

        # Add products
        for idx, product in enumerate(products, start=2):
            try:
                # Basic product info
                ws[f'A{idx}'] = product.get('title', '')
                ws[f'B{idx}'] = product.get('sku', product.get('handle', ''))
                ws[f'C{idx}'] = product.get('price', '')
                ws[f'D{idx}'] = '[Image]'  # Placeholder
                ws[f'E{idx}'] = product.get('description', '')
                ws[f'F{idx}'] = product.get('url', '')

                # Try to embed image
                image_url = product.get('image')
                if image_url:
                    try:
                        img = self._embed_image(ws, image_url, f'D{idx}')
                        if img:
                            log.debug(f"Embedded image for {product.get('title', 'Unknown')}")
                    except Exception as e:
                        log.debug(f"Failed to embed image: {e}")
                        ws[f'D{idx}'] = '[Image not available]'

            except Exception as e:
                log.warning(f"Error processing product {idx}: {e}")
                continue

        # Auto-resize columns
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 12
        ws.column_dimensions['D'].width = 20
        ws.column_dimensions['E'].width = 40
        ws.column_dimensions['F'].width = 50

        # Set row height for images
        for row in range(2, len(products) + 2):
            ws.row_dimensions[row].height = 60

        # Save file
        if not output_path:
            output_path = str(Path(tempfile.gettempdir()) / "products_with_images.xlsx")

        wb.save(output_path)
        log.info(f"Exported to {output_path}")

        return output_path

    def _embed_image(self, worksheet, image_url: str, cell_ref: str):
        """Embed image from URL into Excel cell"""
        try:
            from openpyxl.drawing.image import Image as XLImage

            # Download image
            response = self.session.get(image_url, timeout=10)
            response.raise_for_status()

            # Save to temp file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            temp_file.write(response.content)
            temp_file.close()

            # Insert into Excel
            img = XLImage(temp_file.name)
            img.width = 120
            img.height = 120

            worksheet.add_image(img, cell_ref)
            return img

        except Exception as e:
            log.debug(f"Error embedding image from {image_url}: {e}")
            return None

    def batch_export(self, products_by_collection: Dict[str, List[Dict]], output_folder: str = None) -> Dict[str, str]:
        """
        Export multiple collections to separate Excel files

        Args:
            products_by_collection: Dict of {collection_name: [products]}
            output_folder: Optional output folder

        Returns:
            Dict of {collection_name: file_path}
        """
        if not output_folder:
            output_folder = tempfile.gettempdir()

        results = {}
        for collection, products in products_by_collection.items():
            try:
                output_path = Path(output_folder) / f"{collection}.xlsx"
                file_path = self.export_with_images(products, str(output_path))
                results[collection] = file_path
                log.info(f"Exported {collection}: {len(products)} products")
            except Exception as e:
                log.error(f"Failed to export {collection}: {e}")
                results[collection] = None

        return results

    def export_summary(self, products: List[Dict], output_path: str = None) -> str:
        """
        Export summary report with image links (for faster processing)

        Args:
            products: List of products
            output_path: Optional output path

        Returns:
            Path to Excel file
        """
        try:
            import openpyxl
        except ImportError:
            raise

        log.info(f"Exporting summary for {len(products)} products")

        wb = openpyxl.Workbook()
        ws = wb.active

        # Headers
        headers = ['Product', 'SKU', 'Price', 'Image URL', 'Description']
        ws.append(headers)

        # Add products (links only, no embedding)
        for product in products:
            ws.append([
                product.get('title', ''),
                product.get('sku', ''),
                product.get('price', ''),
                product.get('image', ''),
                product.get('description', '')
            ])

        # Auto-resize columns
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 12
        ws.column_dimensions['D'].width = 50
        ws.column_dimensions['E'].width = 40

        # Save
        if not output_path:
            output_path = str(Path(tempfile.gettempdir()) / "products_summary.xlsx")

        wb.save(output_path)
        log.info(f"Summary exported to {output_path}")

        return output_path
