# Dữ liệu

- Cào dữ liệu [Pháp Điển Việt Nam](https://phapdien.moj.gov.vn/Pages/home.aspx) để xây dựng cấu trúc bộ dữ liệu pháp luật.

- Cào dữ liệu [Văn bản quy phạm pháp luật](https://vbpl.vn/) để lấy dữ liệu.



## Dữ liệu Pháp Điển 

- Giải nén tệp zip tải xuống từ [Pháp Điển Việt Nam](https://phapdien.moj.gov.vn/Pages/home.aspx) vào data_crawler.
- Vào thư mục data_crawler

```
cd data_crawler
```

- Chạy file toJson.js để tạo 3 file json từ jsonData.js:
    - chude.json: các chủ đề.
    - demuc.json: các đề mục.
    - treeNode.json: các điều, chỉ mục, đề mục và chủ đề tương ứng.

```
node toJson.js
```

## Xây dựng cấu trúc luật

- Chạy MySQL và PHPMyAdmin containers từ docker-compose

``` 
docker-compose up -d
```

- Cài đặt các thư viện cần thiết

```
python structure_crawl.py
```

- Lấy cấu trúc các văn bản luật từ pháp điển

```
python structure_crawl.py
```

## Lấy dữ liệu các văn bản pháp luật

- Cào dữ liệu html các văn bản luật
```
python document_crawl.py
```

- Chia các văn bản thành các điều và lưu vào database

```
python build_unit.py
```