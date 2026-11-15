"""Wanderer CAD : langues de l'interface. Noms des outils et des commandes, et alias de la ligne de commande, pour les
langues autres que l'anglais et le français (le français, plus complet, est dans core.py).

Les alias suivent les commandes des versions localisées d'AutoCAD et de Rhino (LINIE, KREIS, SCHIEBEN en allemand ;
LINEA, CIRCULO, DESPLAZA en espagnol...). En chinois, japonais et coréen, AutoCAD et Rhino gardent leurs commandes en
anglais : seuls les noms affichés sont traduits, les alias anglais restent. Les invites des commandes restent en anglais."""

LANGUAGE_ITEMS = (
    ('EN', "English", "Tool names, commands and prompts in English"),
    ('FR', "Français", "Tool names, commands and prompts in French (the English names stay usable in the command line)"),
    ('DE', "Deutsch", "Tool names in German, with the command aliases of German AutoCAD and Rhino (prompts in English)"),
    ('ES', "Español", "Tool names in Spanish, with the command aliases of Spanish AutoCAD and Rhino (prompts in English)"),
    ('IT', "Italiano", "Tool names in Italian, with the command aliases of Italian AutoCAD and Rhino (prompts in English)"),
    ('PT', "Português", "Tool names in Portuguese, with the command aliases of Portuguese AutoCAD (prompts in English)"),
    ('RU', "Русский", "Tool names in Russian, with the command aliases of Russian AutoCAD (prompts in English)"),
    ('TR', "Türkçe", "Tool names in Turkish; the English aliases stay, Turkish command words are added (prompts in English)"),
    ('ZH', "简体中文", "Tool names in Simplified Chinese; aliases stay in English, as in AutoCAD and Rhino (prompts in English)"),
    ('JA', "日本語", "Tool names in Japanese; aliases stay in English, as in AutoCAD and Rhino (prompts in English)"),
    ('KO', "한국어", "Tool names in Korean; aliases stay in English, as in AutoCAD and Rhino (prompts in English)"),
)
LANG_CODES = ('DE', 'ES', 'IT', 'PT', 'RU', 'TR', 'ZH', 'JA', 'KO')        # colonnes de _NAMES, dans cet ordre

# nom anglais | DE | ES | IT | PT | RU | TR | ZH | JA | KO
_NAMES = """
Align|Ausrichten|Alinear|Allinea|Alinhar|Выровнять|Hizala|对齐|整列|정렬
Annotation|Führungslinie|Directriz|Direttrice|Chamada|Выноска|Açıklama|引线标注|引出線|지시선
Arc: 3 Points|Bogen: 3 Punkte|Arco: 3 puntos|Arco: 3 punti|Arco: 3 pontos|Дуга: 3 точки|Yay: 3 nokta|圆弧：三点|円弧：3点|호: 3점
Array: Polar|Anordnung: polar|Matriz: polar|Serie: polare|Matriz: polar|Массив: круговой|Dizi: kutupsal|阵列：环形|配列：円形|배열: 원형
Blend Surface|Fläche überblenden|Mezclar superficies|Raccorda superfici|Mesclar superfícies|Переход поверхностей|Yüzey geçişi|混接曲面|ブレンドサーフェス|곡면 블렌드
Box|Quader|Caja|Parallelepipedo|Caixa|Ящик|Kutu|长方体|直方体|상자
Boolean Union|Boolesche Vereinigung|Unión booleana|Unione booleana|União booleana|Булево объединение|Boole birleşimi|布尔并集|ブール演算：和|불리언 합집합
Camera|Kamera|Cámara|Camera|Câmera|Камера|Kamera|相机|カメラ|카메라
Camera with Target|Kamera mit Ziel|Cámara con objetivo|Camera con bersaglio|Câmera com alvo|Камера с целью|Hedefli kamera|带目标相机|ターゲット付きカメラ|대상 카메라
Cap|Deckflächen|Tapar|Chiudi fori|Tampar|Закрыть торцы|Kapat|加盖|キャップ|캡
Center Mark|Mittelpunktmarke|Marca de centro|Centro|Marca de centro|Маркер центра|Merkez işareti|圆心标记|中心マーク|중심 표식
Chamfer Edge|Kante fasen|Chaflán de borde|Cima bordo|Chanfro de aresta|Фаска ребра|Kenar pahı|边缘斜角|エッジ面取り|모서리 모따기
Chamfer Curve|Fase|Chaflán|Cima|Chanfro|Фаска|Pah|倒角|面取り|모따기
Clipping Plane|Schnittebene|Plano delimitador|Piano di ritaglio|Plano de corte|Секущая плоскость|Kesme düzlemi|截平面|クリッピング平面|클리핑 평면
Dimension|Bemaßung|Cota|Quota|Cota|Размер|Ölçü|标注|寸法|치수
Angular Dimension|Winkelbemaßung|Cota angular|Quota angolare|Cota angular|Угловой размер|Açı ölçüsü|角度标注|角度寸法|각도 치수
Arc Length Dimension|Bogenlängenbemaßung|Cota de longitud de arco|Quota lunghezza arco|Cota de comprimento de arco|Размер длины дуги|Yay uzunluğu ölçüsü|弧长标注|弧長寸法|호 길이 치수
Continue Dimension|Kettenbemaßung|Cota continua|Quota continua|Cota contínua|Размерная цепь|Sürekli ölçü|连续标注|直列寸法|연속 치수
Move Dimension Line|Maßlinie verschieben|Mover línea de cota|Sposta linea di quota|Mover linha de cota|Перенести размерную линию|Ölçü çizgisini taşı|移动尺寸线|寸法線を移動|치수선 이동
Ordinate Dimension|Koordinatenbemaßung|Cota por coordenadas|Quota coordinata|Cota ordenada|Ординатный размер|Ordinat ölçüsü|坐标标注|座標寸法|세로좌표 치수
Radius / Diameter|Radius / Durchmesser|Radio / diámetro|Raggio / diametro|Raio / diâmetro|Радиус / диаметр|Yarıçap / çap|半径 / 直径|半径 / 直径|반지름 / 지름
Split|Teilen|Partir|Suddividi|Dividir|Разделить|Böl|分割|分割|분할
Move|Verschieben|Mover|Sposta|Mover|Перенести|Taşı|移动|移動|이동
Distance|Abstand|Distancia|Distanza|Distância|Расстояние|Mesafe|距离|距離|거리
Divide|Unterteilen|Dividir|Dividi|Dividir em partes|Поделить|Parçalara ayır|等分|ディバイダ|등분할
Edge Surface|Fläche aus Randkurven|Superficie desde bordes|Superficie da bordi|Superfície por bordas|Поверхность по кромкам|Kenarlardan yüzey|边缘曲面|エッジサーフェス|모서리 곡면
Explode|Zerlegen|Descomponer|Esplodi|Explodir|Расчленить|Patlat|分解|分解|분해
Extrude Curve|Kurve extrudieren|Extruir curva|Estrudi curva|Extrudar curva|Выдавить кривую|Eğriyi uzat (ekstrüzyon)|挤出曲线|曲線を押し出し|곡선 돌출
Extrude Along Curve|Entlang Kurve extrudieren|Extruir a lo largo de curva|Estrudi lungo curva|Extrudar ao longo de curva|Выдавить вдоль кривой|Eğri boyunca ekstrüzyon|沿曲线挤出|曲線に沿って押し出し|곡선을 따라 돌출
Extrude Surface|Fläche extrudieren|Extruir superficie|Estrudi superficie|Extrudar superfície|Выдавить поверхность|Yüzey ekstrüzyonu|挤出曲面|サーフェスを押し出し|곡면 돌출
Fillet Curve|Abrunden|Empalme|Raccordo|Concordância|Сопряжение|Yuvarlat|圆角|フィレット|모깎기
Hatch|Schraffur|Sombreado|Tratteggio|Hachura|Штриховка|Tarama|图案填充|ハッチング|해치
Hatch Region|Schraffur per Punkt|Sombreado por punto|Tratteggio per punto|Hachura por ponto|Штриховка по точке|Noktadan tarama|拾取点填充|点指定ハッチング|점 지정 해치
ID Point|Punktkoordinaten|Coordenadas de punto|Coordinate punto|Coordenadas do ponto|Координаты точки|Nokta koordinatı|点坐标|点座標|점 좌표
Join|Verbinden|Unir|Unisci|Unir|Соединить|Birleştir|合并|結合|결합
Area Light|Flächenlicht|Luz de área|Luce area|Luz de área|Площадной свет|Alan ışığı|面光源|エリアライト|면 조명
Point Light|Punktlicht|Luz puntual|Luce puntiforme|Luz pontual|Точечный свет|Nokta ışık|点光源|ポイントライト|점 조명
Spot Light|Spotlicht|Foco|Faretto|Refletor|Прожектор|Spot ışık|聚光灯|スポットライト|스포트 조명
Sun Light|Sonnenlicht|Luz solar|Luce solare|Luz solar|Солнце|Güneş ışığı|太阳光|サンライト|태양 조명
Loft|Loft|Transición|Loft|Elevação|По сечениям|Loft|放样|ロフト|로프트
Make 2D|2D erzeugen|Crear 2D|Crea 2D|Criar 2D|Создать 2D|2B oluştur|建立二维图|2D図を作成|2D 도면 만들기
Match Surface|Fläche anpassen|Igualar superficie|Combina superficie|Combinar superfície|Согласовать поверхность|Yüzey eşle|衔接曲面|サーフェスをマッチング|곡면 일치
Area / Perimeter|Fläche / Umfang|Área / perímetro|Area / perimetro|Área / perímetro|Площадь / периметр|Alan / çevre|面积 / 周长|面積 / 周長|면적 / 둘레
Offset Edge|Kante versetzen|Desfasar borde|Offset bordo|Deslocar aresta|Смещение ребра|Kenar öteleme|偏移边缘|エッジをオフセット|모서리 간격띄우기
Offset Surface|Fläche versetzen|Desfasar superficie|Offset superficie|Deslocar superfície|Смещение поверхности|Yüzey öteleme|偏移曲面|サーフェスをオフセット|곡면 간격띄우기
Overkill|Duplikate bereinigen|Eliminar duplicados|Elimina duplicati|Eliminar duplicados|Удалить дубликаты|Çakışanları temizle|删除重复对象|重複を削除|중복 삭제
Patch|Patch|Parche|Patch|Remendo|Заплатка|Yama|嵌面|パッチ|패치
Plane|Ebene|Plano|Piano|Plano|Плоскость|Düzlem|平面|平面|평면
Planar Surface|Planare Fläche|Superficie plana|Superficie piana|Superfície plana|Плоская поверхность|Düzlemsel yüzey|平面曲面|平面サーフェス|평면 곡면
Polyline|Polylinie|Polilínea|Polilinea|Polilinha|Полилиния|Çoklu çizgi|多段线|ポリライン|폴리선
Project Curve|Kurve projizieren|Proyectar curva|Proietta curva|Projetar curva|Спроецировать кривую|Eğriyi izdüşür|投影曲线|曲線を投影|곡선 투영
Rail Revolve|Schienenrotation|Revolución por carril|Rivoluzione su binario|Revolução por trilho|Вращение по направляющей|Raylı döndürme|沿路径旋转|レール回転|레일 회전
Revolve|Rotation|Revolución|Rivoluzione|Revolução|Вращать|Döndürerek katıla|旋转成形|回転|회전 형성
Select|Auswählen|Seleccionar|Seleziona|Selecionar|Выбрать|Seç|选择|選択|선택
Select Circle|Kreisauswahl|Selección circular|Selezione circolare|Seleção circular|Выбор кругом|Daire ile seç|圆形选择|円形選択|원형 선택
Lasso Select|Lassoauswahl|Selección de lazo|Selezione lazo|Seleção por laço|Выбор лассо|Kement ile seç|套索选择|投げ縄選択|올가미 선택
Select Box|Rechteckauswahl|Selección por ventana|Selezione finestra|Seleção por janela|Выбор рамкой|Kutu ile seç|框选|矩形選択|상자 선택
Shell|Schale|Vaciado|Guscio|Casca|Оболочка|Kabuk|抽壳|シェル|쉘
Split Face|Fläche teilen|Dividir cara|Dividi faccia|Dividir face|Разделить грань|Yüzü böl|分割面|面を分割|면 분할
Surface from Corner Points|Fläche aus Eckpunkten|Superficie por esquinas|Superficie da vertici|Superfície por cantos|Поверхность по углам|Köşe noktalarından yüzey|指定角点建立曲面|コーナー点からサーフェス|모서리 점으로 곡면
Stretch|Strecken|Estirar|Stira|Esticar|Растянуть|Sündür|拉伸|ストレッチ|신축
SubD Box|SubD-Quader|Caja SubD|Parallelepipedo SubD|Caixa SubD|SubD-ящик|SubD kutu|细分长方体|SubD直方体|SubD 상자
SubD Plane|SubD-Ebene|Plano SubD|Piano SubD|Plano SubD|SubD-плоскость|SubD düzlem|细分平面|SubD平面|SubD 평면
Sweep 1 Rail|Sweep 1 Schiene|Barrido por 1 carril|Sweep 1 binario|Varredura 1 trilho|Сдвиг по 1 направляющей|Süpürme 1 ray|单轨扫掠|1レールスイープ|1레일 스윕
Sweep 2 Rails|Sweep 2 Schienen|Barrido por 2 carriles|Sweep 2 binari|Varredura 2 trilhos|Сдвиг по 2 направляющим|Süpürme 2 ray|双轨扫掠|2レールスイープ|2레일 스윕
Text|Text|Texto|Testo|Texto|Текст|Metin|文字|文字|문자
Thicken|Aufdicken|Dar espesor|Ispessisci|Engrossar|Придать толщину|Kalınlaştır|加厚|厚み付け|두께 주기
Torus|Torus|Toroide|Toro|Toroide|Тор|Simit|圆环体|トーラス|토러스
Trim|Trimmen|Recortar|Taglia|Aparar|Обрезать|Buda|修剪|トリム|자르기
Copy|Kopieren|Copiar|Copia|Copiar|Копировать|Kopyala|复制|コピー|복사
Rotate|Drehen|Rotar|Ruota|Rotacionar|Повернуть|Döndür|旋转|回転移動|회전
Scale|Skalieren|Escalar|Scala|Escalar|Масштаб|Ölçekle|缩放|スケール|축척
Scale 2D|Skalieren 2D|Escalar 2D|Scala 2D|Escalar 2D|Масштаб 2D|Ölçekle 2B|二轴缩放|2Dスケール|2D 축척
Scale 1D|Skalieren 1D|Escalar 1D|Scala 1D|Escalar 1D|Масштаб 1D|Ölçekle 1B|单轴缩放|1Dスケール|1D 축척
Scale to Size|Auf Größe skalieren|Escalar a tamaño|Scala a dimensione|Escalar para tamanho|Масштаб до размера|Boyuta ölçekle|缩放到尺寸|サイズに合わせてスケール|크기에 맞춰 축척
Rectangle|Rechteck|Rectángulo|Rettangolo|Retângulo|Прямоугольник|Dikdörtgen|矩形|長方形|직사각형
Mirror|Spiegeln|Reflejar|Specchio|Espelhar|Зеркало|Aynala|镜像|ミラー|대칭
Array: Rectangular|Anordnung: rechteckig|Matriz: rectangular|Serie: rettangolare|Matriz: retangular|Массив: прямоугольный|Dizi: dikdörtgen|阵列：矩形|配列：矩形|배열: 직사각형
Array: Linear|Anordnung: linear|Matriz: lineal|Serie: lineare|Matriz: linear|Массив: линейный|Dizi: doğrusal|阵列：直线|配列：直線|배열: 선형
Fillet Edge|Kante abrunden|Empalme de borde|Raccordo bordo|Concordância de aresta|Скругление ребра|Kenar yuvarlat|边缘圆角|エッジフィレット|모서리 모깎기
Boolean Difference|Boolesche Differenz|Diferencia booleana|Differenza booleana|Diferença booleana|Булево вычитание|Boole farkı|布尔差集|ブール演算：差|불리언 차집합
Boolean Intersection|Boolesche Schnittmenge|Intersección booleana|Intersezione booleana|Interseção booleana|Булево пересечение|Boole kesişimi|布尔交集|ブール演算：交差|불리언 교집합
Boolean Split|Boolesche Teilung|División booleana|Divisione booleana|Divisão booleana|Булево разделение|Boole bölme|布尔分割|ブール演算：分割|불리언 분할
Polygon: Center, Radius|Polygon: Mitte, Radius|Polígono: centro, radio|Poligono: centro, raggio|Polígono: centro, raio|Многоугольник: центр, радиус|Çokgen: merkez, yarıçap|多边形：中心、半径|多角形：中心、半径|다각형: 중심, 반지름
Polygon: Circumscribed|Polygon: umschrieben|Polígono: circunscrito|Poligono: circoscritto|Polígono: circunscrito|Многоугольник: описанный|Çokgen: çevrel|多边形：外切|多角形：外接|다각형: 외접
Polygon: Area|Polygon: Fläche|Polígono: área|Poligono: area|Polígono: área|Многоугольник: площадь|Çokgen: alan|多边形：面积|多角形：面積|다각형: 면적
Polygon: Edge|Polygon: Kante|Polígono: lado|Poligono: lato|Polígono: aresta|Многоугольник: сторона|Çokgen: kenar|多边形：边|多角形：辺|다각형: 변
Polygon: Star|Polygon: Stern|Polígono: estrella|Poligono: stella|Polígono: estrela|Многоугольник: звезда|Çokgen: yıldız|多边形：星形|多角形：星形|다각형: 별
Circle: Center, Radius|Kreis: Mitte, Radius|Círculo: centro, radio|Cerchio: centro, raggio|Círculo: centro, raio|Круг: центр, радиус|Daire: merkez, yarıçap|圆：圆心、半径|円：中心、半径|원: 중심, 반지름
Circle: Diameter|Kreis: Durchmesser|Círculo: diámetro|Cerchio: diametro|Círculo: diâmetro|Круг: диаметр|Daire: çap|圆：直径|円：直径|원: 지름
Ellipse: From Center|Ellipse: von Mitte|Elipse: desde el centro|Ellisse: dal centro|Elipse: a partir do centro|Эллипс: из центра|Elips: merkezden|椭圆：从中心|楕円：中心から|타원: 중심에서
Ellipse: Diameter|Ellipse: Durchmesser|Elipse: diámetro|Ellisse: diametro|Elipse: diâmetro|Эллипс: диаметр|Elips: çap|椭圆：直径|楕円：直径|타원: 지름
Ellipse: From Foci|Ellipse: aus Brennpunkten|Elipse: por focos|Ellisse: dai fuochi|Elipse: pelos focos|Эллипс: по фокусам|Elips: odaklardan|椭圆：从焦点|楕円：焦点から|타원: 초점에서
Ellipse: By Corners|Ellipse: durch Ecken|Elipse: por esquinas|Ellisse: per vertici|Elipse: pelos cantos|Эллипс: по углам|Elips: köşelerden|椭圆：角点|楕円：コーナーから|타원: 모서리로
Arc: Center, Start, End|Bogen: Mitte, Start, Ende|Arco: centro, inicio, fin|Arco: centro, inizio, fine|Arco: centro, início, fim|Дуга: центр, начало, конец|Yay: merkez, başlangıç, bitiş|圆弧：圆心、起点、终点|円弧：中心、始点、終点|호: 중심, 시작, 끝
Cylinder|Zylinder|Cilindro|Cilindro|Cilindro|Цилиндр|Silindir|圆柱体|円柱|원통
Cone|Kegel|Cono|Cono|Cone|Конус|Koni|圆锥体|円錐|원뿔
Truncated Cone|Kegelstumpf|Cono truncado|Tronco di cono|Tronco de cone|Усечённый конус|Kesik koni|圆台|円錐台|원뿔대
Pyramid|Pyramide|Pirámide|Piramide|Pirâmide|Пирамида|Piramit|棱锥|角錐|각뿔
Truncated Pyramid|Pyramidenstumpf|Pirámide truncada|Tronco di piramide|Tronco de pirâmide|Усечённая пирамида|Kesik piramit|棱台|角錐台|각뿔대
Tube|Rohr|Tubo|Tubo|Tubo|Труба|Boru|圆管|チューブ|튜브
Sphere|Kugel|Esfera|Sfera|Esfera|Шар|Küre|球体|球|구
Ellipsoid|Ellipsoid|Elipsoide|Ellissoide|Elipsoide|Эллипсоид|Elipsoit|椭球体|楕円体|타원체
Truncated Sphere|Kugelabschnitt|Esfera truncada|Sfera troncata|Esfera truncada|Усечённый шар|Kesik küre|截球体|切り取り球|잘린 구
SubD Sphere|SubD-Kugel|Esfera SubD|Sfera SubD|Esfera SubD|SubD-шар|SubD küre|细分球体|SubD球|SubD 구
SubD Cylinder|SubD-Zylinder|Cilindro SubD|Cilindro SubD|Cilindro SubD|SubD-цилиндр|SubD silindir|细分圆柱体|SubD円柱|SubD 원통
SubD Cone|SubD-Kegel|Cono SubD|Cono SubD|Cone SubD|SubD-конус|SubD koni|细分圆锥体|SubD円錐|SubD 원뿔
SubD Torus|SubD-Torus|Toroide SubD|Toro SubD|Toroide SubD|SubD-тор|SubD simit|细分圆环体|SubDトーラス|SubD 토러스
To SubD|In SubD umwandeln|A SubD|In SubD|Para SubD|В SubD|SubD'ye çevir|转换为细分|SubDに変換|SubD로 변환
SubD to Mesh|SubD in Polygonnetz|SubD a malla|SubD in mesh|SubD para malha|SubD в сеть|SubD'den ağa|细分转网格|SubDをメッシュに|SubD를 메쉬로
MultiPipe|MultiPipe|MultiPipe|MultiPipe|MultiPipe|MultiPipe|MultiPipe|多重管|マルチパイプ|멀티파이프
Insert Edge|Kante einfügen|Insertar borde|Inserisci bordo|Inserir aresta|Вставить ребро|Kenar ekle|插入边缘|エッジを挿入|모서리 삽입
Control Point Curve|Kontrollpunktkurve|Curva por puntos de control|Curva per punti di controllo|Curva por pontos de controle|Кривая по контрольным точкам|Kontrol noktalı eğri|控制点曲线|制御点指定曲線|제어점 곡선
Interpolate Curve|Interpolierte Kurve|Curva interpolada|Curva interpolata|Curva interpolada|Кривая через точки|Noktalardan geçen eğri|内插点曲线|補間曲線|보간점 곡선
Sketch|Skizze|Boceto|Schizzo|Esboço|Эскиз|Eskiz|徒手画|スケッチ|스케치
Pen|Stift (Bézier)|Pluma (Bézier)|Penna (Bézier)|Caneta (Bézier)|Перо (Безье)|Kalem (Bézier)|钢笔（贝塞尔）|ペン（ベジェ）|펜 (베지어)
Point|Punkt|Punto|Punto|Ponto|Точка|Nokta|点|点|점
SubD Loft|SubD-Loft|Transición SubD|Loft SubD|Elevação SubD|SubD по сечениям|SubD loft|细分放样|SubDロフト|SubD 로프트
SubD Sweep 1|SubD-Sweep 1|Barrido SubD 1|Sweep SubD 1|Varredura SubD 1|SubD-сдвиг 1|SubD süpürme 1|细分单轨扫掠|SubD 1レールスイープ|SubD 1레일 스윕
SubD Sweep 2|SubD-Sweep 2|Barrido SubD 2|Sweep SubD 2|Varredura SubD 2|SubD-сдвиг 2|SubD süpürme 2|细分双轨扫掠|SubD 2レールスイープ|SubD 2레일 스윕
SubD Revolve|SubD-Rotation|Revolución SubD|Rivoluzione SubD|Revolução SubD|SubD-вращение|SubD döndürme|细分旋转成形|SubD回転|SubD 회전
Network Surface|Fläche aus Kurvennetz|Superficie desde red de curvas|Superficie da rete di curve|Superfície por rede de curvas|Поверхность по сети кривых|Eğri ağından yüzey|网线曲面|ネットワークサーフェス|네트워크 곡면
Fillet Surface|Flächen abrunden|Empalme de superficies|Raccordo superfici|Concordância de superfícies|Сопряжение поверхностей|Yüzey yuvarlat|曲面圆角|サーフェスフィレット|곡면 모깎기
Chamfer Surface|Flächen fasen|Chaflán de superficies|Cima superfici|Chanfro de superfícies|Фаска поверхностей|Yüzey pahı|曲面斜角|サーフェス面取り|곡면 모따기
Extend Surface|Fläche verlängern|Extender superficie|Estendi superficie|Estender superfície|Удлинить поверхность|Yüzeyi uzat|延伸曲面|サーフェスを延長|곡면 연장
Split at Isocurve|An Isokurve teilen|Partir por isocurva|Suddividi su isocurva|Dividir na isocurva|Разделить по изокривой|İzo eğriden böl|以结构线分割|アイソカーブで分割|아이소커브에서 분할
Rebuild Curve|Kurve neu aufbauen|Reconstruir curva|Ricostruisci curva|Reconstruir curva|Перестроить кривую|Eğriyi yeniden oluştur|重建曲线|曲線をリビルド|곡선 재생성
Simplify Curve|Kurve vereinfachen|Simplificar curva|Semplifica curva|Simplificar curva|Упростить кривую|Eğriyi sadeleştir|简化曲线|曲線を単純化|곡선 단순화
Change Degree|Grad ändern|Cambiar grado|Cambia grado|Alterar grau|Изменить степень|Dereceyi değiştir|更改阶数|次数を変更|차수 변경
Insert Control Point|Kontrollpunkt einfügen|Insertar punto de control|Inserisci punto di controllo|Inserir ponto de controle|Вставить контрольную точку|Kontrol noktası ekle|插入控制点|制御点を挿入|제어점 삽입
Remove Control Point|Kontrollpunkt entfernen|Eliminar punto de control|Rimuovi punto di controllo|Remover ponto de controle|Удалить контрольную точку|Kontrol noktası sil|移除控制点|制御点を削除|제어점 제거
Match Curve|Kurve anpassen|Igualar curva|Combina curva|Combinar curva|Согласовать кривую|Eğri eşle|衔接曲线|曲線をマッチング|곡선 일치
Blend Curve|Kurve überblenden|Mezclar curvas|Raccorda curve|Mesclar curvas|Переходная кривая|Eğri geçişi|混接曲线|ブレンド曲線|곡선 블렌드
Block|Block|Bloque|Blocco|Bloco|Блок|Blok|图块|ブロック|블록
Insert Block|Block einfügen|Insertar bloque|Inserisci blocco|Inserir bloco|Вставить блок|Blok ekle|插入图块|ブロックを挿入|블록 삽입
Untrim|Trimmung aufheben|Deshacer recorte|Annulla taglio|Desfazer aparo|Отменить обрезку|Budamayı geri al|取消修剪|アントリム|자르기 해제
Untrim Holes|Löcher schließen|Quitar agujeros|Rimuovi fori|Remover furos|Убрать отверстия|Delikleri kapat|取消修剪洞|穴をアントリム|구멍 자르기 해제
Construction Line|Konstruktionslinie|Línea auxiliar|Linea di costruzione|Linha de construção|Прямая|Yapı çizgisi|构造线|構築線|구성선
Extrude|Extrudieren|Extruir|Estrudi|Extrudar|Выдавить|Ekstrüzyon|挤出|押し出し|돌출
Pipe|Rohr (Pipe)|Tubería|Tubo (Pipe)|Tubulação|Труба по кривой|Boru (eğri boyunca)|圆管（沿曲线）|パイプ|파이프
Intersect|Verschneiden|Intersección de objetos|Intersezione oggetti|Interseção de objetos|Пересечение объектов|Nesne kesişimi|物件交集|交線|교차선
Section|Schnitt|Sección|Sezione|Seção|Сечение|Kesit|截面线|断面曲線|단면
Contour|Kontur|Contorno|Contorno|Contorno|Контуры|Kontur|等距断面线|等高線|등고선
Extract Surface|Fläche extrahieren|Extraer superficie|Estrai superficie|Extrair superfície|Извлечь поверхность|Yüzey çıkar|抽离曲面|サーフェスを抽出|곡면 추출
Duplicate Border|Rand duplizieren|Duplicar borde|Duplica contorno|Duplicar borda|Дублировать границу|Sınırı çoğalt|复制边框|境界を複製|경계 복제
Duplicate Edge|Kante duplizieren|Duplicar arista|Duplica bordo|Duplicar aresta|Дублировать ребро|Kenarı çoğalt|复制边缘|エッジを複製|모서리 복제
Duplicate Face Border|Flächenrand duplizieren|Duplicar borde de cara|Duplica contorno faccia|Duplicar borda da face|Дублировать границу грани|Yüz sınırını çoğalt|复制面的边框|面の境界を複製|면 경계 복제
Merge All Faces|Koplanare Flächen vereinen|Fusionar caras coplanares|Unisci facce complanari|Mesclar faces coplanares|Объединить грани в плоскости|Eş düzlemli yüzleri birleştir|合并共面的面|同一平面上の面をマージ|동일 평면 면 병합
Unroll Surface|Fläche abwickeln|Desarrollar superficie|Sviluppa superficie|Planificar superfície|Развернуть поверхность|Yüzeyi aç|展开曲面|サーフェスを展開|곡면 전개
Rebuild Surface|Fläche neu aufbauen|Reconstruir superficie|Ricostruisci superficie|Reconstruir superfície|Перестроить поверхность|Yüzeyi yeniden oluştur|重建曲面|サーフェスをリビルド|곡면 재생성
Orient|Orientieren|Orientar|Orienta|Orientar|Ориентировать|Yönlendir|定位|配置（2点）|방향 맞추기
Extend Curve|Kurve verlängern|Alargar curva|Estendi curva|Estender curva|Удлинить кривую|Eğriyi uzat|延伸曲线|曲線を延長|곡선 연장
Layout|Layout|Presentación|Layout|Layout|Лист|Pafta|布局|レイアウト|배치
Viewport|Ansichtsfenster|Ventana gráfica|Finestra|Viewport|Видовой экран|Görünüm penceresi|视口|ビューポート|뷰포트
Auto CPlane|Auto-KEbene|PlanoC automático|PianoC automatico|PlanoC automático|Авто КПлоск|Otomatik çalışma düzlemi|自动工作平面|自動作業平面|자동 작업평면
PushPull|Drücken/Ziehen|Empujar/tirar|Spingi/tira|Empurrar/puxar|Тянуть/толкать|İt/çek|推拉|プッシュプル|밀기/끌기
CPlane|KEbene|PlanoC|PianoC|PlanoC|КПлоск|Çalışma düzlemi|工作平面|作業平面|작업평면
CPlane 3 Points|KEbene 3 Punkte|PlanoC 3 puntos|PianoC 3 punti|PlanoC 3 pontos|КПлоск 3 точки|Çalışma düzlemi 3 nokta|工作平面：三点|作業平面：3点|작업평면 3점
CPlane Vertical|KEbene vertikal|PlanoC vertical|PianoC verticale|PlanoC vertical|КПлоск вертикально|Çalışma düzlemi dikey|工作平面：垂直|作業平面：垂直|작업평면 수직
CPlane View|KEbene Ansicht|PlanoC vista|PianoC vista|PlanoC vista|КПлоск по виду|Çalışma düzlemi görünüm|工作平面：视图|作業平面：ビュー|작업평면 뷰
CPlane Top|KEbene oben|PlanoC superior|PianoC superiore|PlanoC superior|КПлоск сверху|Çalışma düzlemi üst|工作平面：顶|作業平面：上|작업평면 위
CPlane Front|KEbene vorne|PlanoC frontal|PianoC frontale|PlanoC frontal|КПлоск спереди|Çalışma düzlemi ön|工作平面：前|作業平面：正面|작업평면 정면
CPlane Right|KEbene rechts|PlanoC derecha|PianoC destra|PlanoC direita|КПлоск справа|Çalışma düzlemi sağ|工作平面：右|作業平面：右|작업평면 오른쪽
CPlane Back|KEbene hinten|PlanoC posterior|PianoC posteriore|PlanoC posterior|КПлоск сзади|Çalışma düzlemi arka|工作平面：后|作業平面：背面|작업평면 뒤
CPlane Left|KEbene links|PlanoC izquierda|PianoC sinistra|PlanoC esquerda|КПлоск слева|Çalışma düzlemi sol|工作平面：左|作業平面：左|작업평면 왼쪽
CPlane Bottom|KEbene unten|PlanoC inferior|PianoC inferiore|PlanoC inferior|КПлоск снизу|Çalışma düzlemi alt|工作平面：底|作業平面：下|작업평면 아래
CPlane Elevation|KEbene Höhe|Elevación de PlanoC|Elevazione PianoC|Elevação do PlanoC|Уровень КПлоск|Çalışma düzlemi yüksekliği|工作平面高度|作業平面の高さ|작업평면 높이
Undo|Rückgängig|Deshacer|Annulla|Desfazer|Отменить|Geri al|撤销|元に戻す|실행 취소
Redo|Wiederherstellen|Rehacer|Ripeti|Refazer|Повторить|Yinele|重做|やり直し|다시 실행
Delete|Löschen|Borrar|Cancella|Apagar|Стереть|Sil|删除|削除|삭제
Alias Editor|Alias-Editor|Editor de alias|Editor di alias|Editor de aliases|Редактор псевдонимов|Kısaltma düzenleyici|别名编辑器|エイリアス編集|별칭 편집기
Select All|Alles auswählen|Seleccionar todo|Seleziona tutto|Selecionar tudo|Выбрать всё|Tümünü seç|全选|すべて選択|모두 선택
Select None|Auswahl aufheben|Deseleccionar todo|Deseleziona tutto|Desmarcar tudo|Снять выбор|Seçimi kaldır|取消选择|選択解除|선택 해제
Invert Selection|Auswahl umkehren|Invertir selección|Inverti selezione|Inverter seleção|Инвертировать выбор|Seçimi ters çevir|反选|選択を反転|선택 반전
Hide|Ausblenden|Ocultar|Nascondi|Ocultar|Скрыть|Gizle|隐藏|非表示|숨기기
Isolate|Isolieren|Aislar|Isola|Isolar|Изолировать|Yalıt|隔离|選択オブジェクトのみ表示|분리
Show All|Alles einblenden|Mostrar todo|Mostra tutto|Mostrar tudo|Показать всё|Tümünü göster|全部显示|すべて表示|모두 표시
Zoom Extents|Zoom Grenzen|Zoom extensión|Zoom estensioni|Zoom extensão|Показать всё (зум)|Tümünü sığdır|缩放至全部|全体表示|범위 줌
Zoom Selected|Zoom Auswahl|Zoom selección|Zoom selezione|Zoom seleção|Зум на выбранное|Seçime yakınlaş|缩放至选取|選択オブジェクトをズーム|선택 줌
Perspective / Ortho|Perspektive / Parallel|Perspectiva / paralela|Prospettiva / parallela|Perspectiva / paralela|Перспектива / параллельная|Perspektif / paralel|透视 / 平行|パース / 平行|원근 / 평행
Wireframe|Drahtmodell|Alámbrico|Wireframe|Aramado|Каркас|Tel kafes|线框|ワイヤフレーム|와이어프레임
Shaded|Schattiert|Sombreado (vista)|Ombreggiata|Sombreado (vista)|Тонированный|Gölgeli|着色|シェーディング|음영
Rendered|Gerendert|Renderizado|Renderizzata|Renderizado|Визуализация|Render|渲染|レンダリング|렌더
X-Ray|Röntgen|Rayos X|Raggi X|Raio X|Рентген|X-ışını|透明|X線|X-레이
Grid|Raster|Rejilla|Griglia|Grade|Сетка|Izgara|网格|グリッド|그리드
Save|Speichern|Guardar|Salva|Salvar|Сохранить|Kaydet|保存|保存|저장
Group|Gruppieren|Agrupar|Raggruppa|Agrupar|Группа|Grupla|群组|グループ化|그룹
Ungroup|Gruppierung aufheben|Desagrupar|Separa|Desagrupar|Разгруппировать|Grubu çöz|解散群组|グループ解除|그룹 해제
Block Edit|Block bearbeiten|Editar bloque|Modifica blocco|Editar bloco|Редактировать блок|Blok düzenle|编辑图块|ブロック編集|블록 편집
Explode Block|Block zerlegen|Descomponer bloque|Esplodi blocco|Explodir bloco|Расчленить блок|Bloğu patlat|分解图块|ブロックを分解|블록 분해
Model|Modell|Modelo|Modello|Modelo|Модель|Model|模型|モデル|모형
Paper Space|Papierbereich|Espacio papel|Spazio carta|Espaço do papel|Пространство листа|Kağıt uzayı|图纸空间|ペーパー空間|도면 공간
Page Setup|Seiteneinrichtung|Configurar página|Imposta pagina|Configurar página|Параметры листа|Sayfa düzeni|页面设置|ページ設定|페이지 설정
Export PDF|PDF exportieren|Exportar PDF|Esporta PDF|Exportar PDF|Экспорт PDF|PDF dışa aktar|导出 PDF|PDFを書き出し|PDF 내보내기
Export SVG|SVG exportieren|Exportar SVG|Esporta SVG|Exportar SVG|Экспорт SVG|SVG dışa aktar|导出 SVG|SVGを書き出し|SVG 내보내기
Export DXF|DXF exportieren|Exportar DXF|Esporta DXF|Exportar DXF|Экспорт DXF|DXF dışa aktar|导出 DXF|DXFを書き出し|DXF 내보내기
Export DWG|DWG exportieren|Exportar DWG|Esporta DWG|Exportar DWG|Экспорт DWG|DWG dışa aktar|导出 DWG|DWGを書き出し|DWG 내보내기
Import DXF / DWG|DXF / DWG importieren|Importar DXF / DWG|Importa DXF / DWG|Importar DXF / DWG|Импорт DXF / DWG|DXF / DWG içe aktar|导入 DXF / DWG|DXF / DWGを読み込み|DXF / DWG 가져오기
Weld|Verschweißen|Soldar|Salda|Soldar|Сварить|Kaynakla|焊接|ウェルド|용접
Bridge|Brücke|Puente|Ponte|Ponte|Мост|Köprü|桥接|ブリッジ|브리지
Fill|Füllen|Rellenar|Riempi|Preencher|Заполнить|Doldur|填补|穴埋め|채우기
Crease|Knick|Pliegue|Piega|Vinco|Складка|Kırışık|锐边|折り目|주름
Select Loop|Schleife auswählen|Seleccionar bucle|Seleziona loop|Selecionar laço de arestas|Выбрать петлю|Döngü seç|选择循环边|ループ選択|루프 선택
Select Ring|Ring auswählen|Seleccionar anillo|Seleziona anello|Selecionar anel|Выбрать кольцо|Halka seç|选择环形边|リング選択|링 선택
Top|Oben|Superior|Superiore|Superior|Сверху|Üst|顶视图|上面|위
Front|Vorne|Frontal|Frontale|Frontal|Спереди|Ön|前视图|正面|정면
Right|Rechts|Derecha|Destra|Direita|Справа|Sağ|右视图|右面|오른쪽
Back|Hinten|Posterior|Posteriore|Posterior|Сзади|Arka|后视图|背面|뒤
Left|Links|Izquierda|Sinistra|Esquerda|Слева|Sol|左视图|左面|왼쪽
Bottom|Unten|Inferior|Inferiore|Inferior|Снизу|Alt|底视图|下面|아래
Perspective|Perspektive|Perspectiva|Prospettiva|Perspectiva|Перспектива|Perspektif|透视图|パース|원근
"""

# alias par langue : nom anglais | alias (séparés par des espaces). Les alias anglais restent utilisables quand ils ne sont
# pas déjà pris par un alias de la langue.
_ALIASES = """
[DE]
Polyline|l linie pl plinie polylinie
Circle: Center, Radius|k kreis
Arc: Center, Start, End|b bogen
Arc: 3 Points|b3 bogen3
Rectangle|re rechteck
Ellipse: From Center|el ellipse
Polygon: Center, Radius|pg polygon vieleck
Point|pu punkt
Control Point Curve|spl spline kurve
Construction Line|kl klinie
Move|s schieben verschieben
Copy|ko kopieren
Rotate|dr drehen
Scale|v varia skalieren
Mirror|sp spiegeln
Stretch|str strecken
Trim|su stutzen trimmen
Extend Curve|de dehnen verlängern
Offset Edge|vs versetz versetzen
Fillet Curve|ar abrunden
Chamfer Curve|fa fase
Fillet Edge|kantenabrunden
Chamfer Edge|kantenfase
Array: Rectangular|rh reihe anordnung
Array: Polar|reihepolar
Array: Linear|reihelinear
Explode|ur ursprung zerlegen
Join|vb verbinden
Split|bruch teilen
Divide|tl unterteilen messen
Hatch|sch schraff schraffur
Delete|lö löschen
Dimension|bli bemlinear bem
Angular Dimension|bemwinkel
Radius / Diameter|bemradius bemdurchm
Annotation|führung mführung
Text|t text mtext
Distance|ab abstand
Area / Perimeter|fläche umfang
ID Point|id
Block|bl block
Insert Block|ein einfüge
Extrude Curve|ext extrusion
Revolve|rot rotation
Loft|anheben loft
Sweep 1 Rail|sweep
Boolean Union|ver vereinig
Boolean Difference|dif differenz
Boolean Intersection|sm schnittmenge
Box|quader
Cylinder|zyl zylinder
Cone|kegel
Sphere|kugel
Torus|torus
Pyramid|pyramide
Thicken|dicke aufdicken
Planar Surface|region planfläche
Zoom Extents|z zoom zoomgrenzen
Undo|zurück rückgängig
Select All|alles
Layout|layout
Alias Editor|aliasedit
[ES]
Polyline|l linea pl pol polilinea
Circle: Center, Radius|c circulo
Arc: Center, Start, End|a arco
Arc: 3 Points|a3 arco3
Rectangle|rec rectang rectangulo
Ellipse: From Center|el elipse
Polygon: Center, Radius|pg poligono
Point|pu punto
Control Point Curve|spl spline curva
Construction Line|xl lineax
Move|d desplaza mover
Copy|cp copia copiar
Rotate|gi gira rotar
Scale|ec escala escalar
Mirror|si simetria reflejar
Stretch|et estira estirar
Trim|rr recorta recortar
Extend Curve|al alarga alargar extender
Offset Edge|df desfase desfasar
Fillet Curve|mp empalme empalmar
Chamfer Curve|ch chaflan
Fillet Edge|empalmeborde
Chamfer Edge|chaflanborde
Array: Rectangular|ma matriz
Array: Polar|matrizpolar
Array: Linear|matrizlineal
Explode|dp descomp descomponer
Join|u unir
Split|parte partir
Divide|div divide gradua
Hatch|sb sombrea sombreado
Delete|b borra borrar
Dimension|acolineal cota acotar
Angular Dimension|acoangulo
Radius / Diameter|acoradio acodiametro
Annotation|directriz
Text|t texto textom
Distance|di dist distancia
Area / Perimeter|area
ID Point|id
Block|bq bloque
Insert Block|in insert insertar
Extrude Curve|ext extrusion extruir
Revolve|rev revolucion
Loft|solevacion transicion
Sweep 1 Rail|barrer barrido
Boolean Union|uni union
Boolean Difference|dif diferencia
Boolean Intersection|inter intersec
Box|caja prismarect
Cylinder|cil cilindro
Cone|cono
Sphere|esfera
Torus|toroide
Pyramid|piramide
Thicken|espesor
Planar Surface|region superficieplana
Zoom Extents|z zoom zoomextension
Undo|h deshacer
Select All|todo
Layout|presentacion
Alias Editor|aliasedit
[IT]
Polyline|l linea pl plinea polilinea
Circle: Center, Radius|c cerchio
Arc: Center, Start, End|a arco
Arc: 3 Points|a3 arco3
Rectangle|rec rettangolo
Ellipse: From Center|el ellisse
Polygon: Center, Radius|pg poligono
Point|pu punto
Control Point Curve|spl spline curva
Construction Line|xl xlinea
Move|s sposta
Copy|cp copia
Rotate|ru ruota
Scale|sc scala
Mirror|sp specchio
Stretch|st stira
Trim|ta taglia
Extend Curve|es estendi
Offset Edge|o offset
Fillet Curve|ra raccordo
Chamfer Curve|ci cima
Fillet Edge|raccordobordo
Chamfer Edge|cimabordo
Array: Rectangular|se serie
Array: Polar|seriepolare
Array: Linear|serielineare
Explode|x esplodi
Join|u unisci
Split|spezza suddividi
Divide|div dividi misura
Hatch|tr tratteggio
Delete|ca cancella
Dimension|dli dimlineare quota
Angular Dimension|dimangolo
Radius / Diameter|dimraggio dimdiametro
Annotation|direttrice
Text|t testo testom
Distance|di dist distanza
Area / Perimeter|area
ID Point|id
Block|b blocco
Insert Block|i inser inserisci
Extrude Curve|est estrudi
Revolve|riv rivoluzione
Loft|loft
Sweep 1 Rail|sweep
Boolean Union|uni unione
Boolean Difference|so sottrai
Boolean Intersection|int intersezione
Box|parallelepipedo
Cylinder|cil cilindro
Cone|cono
Sphere|sfera
Torus|toro
Pyramid|piramide
Thicken|ispessisci
Planar Surface|regione superficiepiana
Zoom Extents|z zoom zoomestensioni
Undo|annulla
Select All|tutto
Layout|layout
Alias Editor|aliasedit
[PT]
Polyline|l linha pl plinha polilinha
Circle: Center, Radius|c circulo
Arc: Center, Start, End|a arco
Arc: 3 Points|a3 arco3
Rectangle|rec retangulo
Ellipse: From Center|el elipse
Polygon: Center, Radius|pg poligono
Point|po ponto
Control Point Curve|spl spline curva
Construction Line|xl xlinha
Move|m mover
Copy|co cp copiar
Rotate|ro rotacionar girar
Scale|es escala escalar
Mirror|esp espelhar
Stretch|e esticar
Trim|ap aparar
Extend Curve|est estender
Offset Edge|des desloc deslocamento
Fillet Curve|con concord concordancia
Chamfer Curve|ch chanfro
Fillet Edge|concordaresta
Chamfer Edge|chanfroaresta
Array: Rectangular|ma matriz
Array: Polar|matrizpolar
Array: Linear|matrizlinear
Explode|x explodir
Join|u unir
Split|quebra dividir
Divide|div medir
Hatch|h hachura
Delete|ag apagar
Dimension|dli dimlinear cota
Angular Dimension|dimangular
Radius / Diameter|dimraio dimdiametro
Annotation|chamada
Text|t texto textom
Distance|di dist distancia
Area / Perimeter|area
ID Point|id
Block|b bloco
Insert Block|i inserir
Extrude Curve|ext extrusao extrudar
Revolve|rev revolucao
Loft|elevacao
Sweep 1 Rail|varredura
Boolean Union|uni uniao
Boolean Difference|su subtrair
Boolean Intersection|int interseccao
Box|caixa
Cylinder|cil cilindro
Cone|cone
Sphere|esfera
Torus|toroide
Pyramid|piramide
Thicken|engrossar
Planar Surface|regiao superficieplana
Zoom Extents|z zoom zoomextensao
Undo|d desfazer
Select All|tudo
Layout|layout
Alias Editor|aliasedit
[RU]
Polyline|от отрезок пл плиния полилиния
Circle: Center, Radius|к круг
Arc: Center, Start, End|д дуга
Arc: 3 Points|д3 дуга3
Rectangle|пря прямоуг прямоугольник
Ellipse: From Center|эл эллипс
Polygon: Center, Radius|мн многоугольник
Point|то точка
Control Point Curve|спл сплайн кривая
Construction Line|пр прямая
Move|п перенести
Copy|кп копировать
Rotate|пов повернуть
Scale|мш масштаб
Mirror|зер зеркало
Stretch|рас растянуть
Trim|обр обрезать
Extend Curve|у удлинить
Offset Edge|под подобие смещение
Fillet Curve|соп сопряжение
Chamfer Curve|фас фаска
Fillet Edge|скругление
Chamfer Edge|фаскаребра
Array: Rectangular|мас массив
Array: Polar|массивкруг
Array: Linear|массивлин
Explode|расч расчленить
Join|сое соединить
Split|разорвать разделить
Divide|поделить разметить
Hatch|шт штрих штриховка
Delete|с стереть
Dimension|рзм рзмлинейный размер
Angular Dimension|рзмугловой
Radius / Diameter|рзмрадиус рзмдиаметр
Annotation|выноска мвыноска
Text|т текст мтекст
Distance|ди дист расстояние
Area / Perimeter|площадь
ID Point|коорд
Block|б блок
Insert Block|в вставить
Extrude Curve|выд выдавить
Revolve|вращать
Loft|посечениям
Sweep 1 Rail|сдвиг
Boolean Union|объ объединение
Boolean Difference|выч вычитание
Boolean Intersection|пер пересечение
Box|ящик
Cylinder|цилиндр
Cone|конус
Sphere|шар
Torus|тор
Pyramid|пирамида
Thicken|толщина
Planar Surface|область
Zoom Extents|пок показать
Undo|о отменить
Select All|все
Layout|лист
Alias Editor|псевдонимы
[TR]
Polyline|cizgi coklucizgi
Circle: Center, Radius|daire cember
Arc: Center, Start, End|yay
Rectangle|dikdortgen
Ellipse: From Center|elips
Polygon: Center, Radius|cokgen
Point|nokta
Control Point Curve|egri
Construction Line|yapicizgisi
Move|tasi
Copy|kopyala
Rotate|dondur
Scale|olcekle olcek
Mirror|aynala
Stretch|sundur
Trim|buda
Extend Curve|uzat
Offset Edge|otele oteleme
Fillet Curve|yuvarlat
Chamfer Curve|pah
Array: Rectangular|dizi
Explode|patlat
Join|birlestir
Split|bol
Hatch|tarama
Delete|sil
Dimension|olcu
Text|metin yazi
Distance|mesafe
Area / Perimeter|alan
Block|blok
Insert Block|blokekle
Extrude Curve|ekstruzyon katila
Revolve|dondurerekkatila
Boolean Union|birlesim
Boolean Difference|fark cikar
Boolean Intersection|kesisim
Box|kutu
Cylinder|silindir
Cone|koni
Sphere|kure
Torus|simit
Pyramid|piramit
Undo|gerial
Select All|tumunusec
Alias Editor|kisaltma
"""


def _build():
    labels = {c: {} for c in LANG_CODES}
    for line in _NAMES.strip().split("\n"):
        cells = line.split("|")
        if len(cells) != len(LANG_CODES) + 1:
            continue
        for code, text in zip(LANG_CODES, cells[1:]):
            if text.strip():
                labels[code][cells[0]] = text.strip()
    aliases = {c: {} for c in LANG_CODES}
    code = None
    for line in _ALIASES.strip().split("\n"):
        if line.startswith("[") and line.endswith("]"):
            code = line[1:-1]
        elif code in aliases and "|" in line:
            key, al = line.split("|", 1)
            aliases[code][key] = al.strip()
    return labels, aliases


LANG_LABELS, LANG_ALIASES = _build()


def _late_imports():
    pass
