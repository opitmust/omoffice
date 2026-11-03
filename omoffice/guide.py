"""Yazı türleri kataloğu, bölüm rehberi, örnek ifadeler ve kaynak biçimlendirme."""
import re

from .common import turkish_lower

CATEGORIES = ["Akademik", "Eğitim", "İş ve Resmî", "Kişisel"]

# Sihirbazda sorulacak alanlar
FIELD_LABELS = {
    "title": "Başlık", "author": "Yazar(lar)", "institution": "Kurum / Üniversite",
    "department": "Bölüm / Anabilim Dalı", "course": "Ders adı", "instructor": "Öğretim üyesi",
    "advisor": "Danışman", "student_no": "Öğrenci numarası", "degree": "Derece (ör. Yüksek Lisans Tezi)",
    "recipient": "Alıcı (kurum / kişi)", "subject": "Konu", "date": "Tarih", "keywords": "Anahtar kelimeler",
}

KINDS = {
    "makale": {
        "name": "Bilimsel Makale", "category": "Akademik", "icon": "",
        "desc": "Dergiye gönderilecek araştırma makalesi (IMRaD düzeni: Giriş–Yöntem–Bulgular–Tartışma).",
        "fields": ["title", "author", "institution", "keywords"], "citation": True,
        "sections": [
            ("Özet", 1, "150–250 sözcükle amacı, yöntemi, temel bulguyu ve sonucu tek paragrafta özetleyin."),
            ("Abstract", 1, "Özetin İngilizce karşılığı (isteğe bağlı, çoğu dergi ister)."),
            ("Giriş", 1, "Konunun önemini, literatürdeki boşluğu ve çalışmanın amacını/araştırma sorusunu yazın."),
            ("Yöntem", 1, "Çalışma deseni, katılımcılar/örneklem, veri toplama araçları ve analiz yöntemi."),
            ("Bulgular", 1, "Sonuçları yorum katmadan sunun; tablo ve şekillere metinde atıf yapın."),
            ("Tartışma", 1, "Bulguları literatürle karşılaştırın, olası açıklamaları ve sınırlılıkları belirtin."),
            ("Sonuç", 1, "Temel çıkarımı ve gelecekteki çalışmalar için önerileri kısaca yazın."),
            ("Kaynakça", 1, "Metinde atıf yapılan tüm kaynaklar, seçilen atıf stilinde."),
        ],
        "tips": ["Başlık 10–15 sözcüğü geçmesin; ana değişkenleri içersin.",
                 "Her paragraf tek bir ana fikri işlesin; ilk cümle o fikri söylesin.",
                 "Bilimsel dilde edilgen ya da birinci çoğul kip ('incelenmiştir', 'inceledik') tutarlı kullanılmalı.",
                 "Tüm tablo ve şekillere metinde numarasıyla atıf yapın (Tablo 1, Şekil 2)."],
    },
    "arastirma": {
        "name": "Bilimsel Araştırma Raporu", "category": "Akademik", "icon": "",
        "desc": "Proje ya da saha araştırmasının ayrıntılı raporu: literatür, yöntem, bulgular ve öneriler.",
        "fields": ["title", "author", "institution", "date", "keywords"], "citation": True, "cover": True, "toc": True,
        "sections": [
            ("Özet", 1, "Araştırmanın amacı, yöntemi, temel bulguları ve önerileri (200–300 sözcük)."),
            ("Giriş", 1, "Problem durumu, araştırmanın amacı ve önemi."),
            ("Problem Cümlesi ve Alt Problemler", 2, "Araştırmanın yanıt aradığı ana soru ve alt sorular."),
            ("Varsayımlar ve Sınırlılıklar", 2, "Çalışmanın dayandığı kabuller ve kapsam sınırları."),
            ("Kuramsal Çerçeve ve İlgili Araştırmalar", 1, "Konuyla ilgili kuramlar ve önceki çalışmaların eleştirel özeti."),
            ("Yöntem", 1, "Araştırma modeli ve izlenen yol."),
            ("Evren ve Örneklem", 2, "Kimlerle, kaç kişiyle ve nasıl seçilerek çalışıldığı."),
            ("Veri Toplama Araçları", 2, "Anket, ölçek, görüşme formu vb. ve geçerlik-güvenirlik bilgileri."),
            ("Verilerin Analizi", 2, "Kullanılan istatistiksel/nitel analiz teknikleri ve yazılımlar."),
            ("Bulgular", 1, "Alt problemlere göre sırayla bulgular; tablolarla destekleyin."),
            ("Tartışma", 1, "Bulguların literatürle karşılaştırılması ve yorumlanması."),
            ("Sonuç ve Öneriler", 1, "Uygulamaya ve sonraki araştırmalara yönelik öneriler."),
            ("Kaynakça", 1, "Atıf yapılan tüm kaynaklar."),
            ("Ekler", 1, "Veri toplama araçları, izin belgeleri, ek tablolar."),
        ],
        "tips": ["Her alt probleme bulgularda ayrı bir başlıkla yanıt verin.",
                 "Etik kurul izni aldıysanız yöntemde tarih ve sayısıyla belirtin.",
                 "Sayısal bulgularda ölçek (n, ort., ss, p) değerlerini tutarlı biçimde yazın."],
    },
    "tez": {
        "name": "Tez (Lisans / Yüksek Lisans / Doktora)", "category": "Akademik", "icon": "",
        "desc": "Kapak, özet, içindekiler ve bölümleriyle tam tez iskeleti. Enstitü yazım kılavuzunuzu da kontrol edin.",
        "fields": ["title", "author", "institution", "department", "advisor", "degree", "date"],
        "citation": True, "cover": True, "toc": True,
        "sections": [
            ("Önsöz", 1, "Teşekkürler ve tezin hazırlanma süreci (1 sayfayı geçmesin)."),
            ("Özet", 1, "Amaç, yöntem, bulgular ve sonuç; 250–500 sözcük. Altına 3–5 anahtar kelime."),
            ("Abstract", 1, "Özetin İngilizcesi ve 'Keywords'."),
            ("1. Giriş", 1, "Problem durumu, amaç, önem, varsayımlar, sınırlılıklar ve tanımlar."),
            ("2. Kavramsal Çerçeve ve Literatür", 1, "Kuramlar ve ilgili çalışmaların sentezi; boşluğu gösterin."),
            ("3. Yöntem", 1, "Araştırma modeli, evren-örneklem, veri toplama araçları ve analiz."),
            ("4. Bulgular", 1, "Araştırma sorularına göre düzenlenmiş bulgular."),
            ("5. Tartışma", 1, "Bulguların yorumu ve literatürle karşılaştırılması."),
            ("6. Sonuç ve Öneriler", 1, "Ana sonuçlar; uygulayıcılara ve araştırmacılara öneriler."),
            ("Kaynakça", 1, "Enstitünün istediği atıf stilinde tüm kaynaklar."),
            ("Ekler", 1, "Ölçekler, izinler, ham veri özetleri."),
            ("Özgeçmiş", 1, "Kısa akademik özgeçmiş (birçok enstitü ister)."),
        ],
        "tips": ["Enstitü yazım kılavuzundaki kenar boşluğu, yazı tipi ve satır aralığı kurallarına uyun "
                 "(çoğunlukla 12 punto, 1,5 satır aralığı).",
                 "Bölüm başlıklarını Başlık 1, alt başlıkları Başlık 2/3 stiliyle yazın; içindekiler otomatik oluşur.",
                 "Her bölüm yeni sayfada başlasın (Ekle › Sayfa Sonu).",
                 "İntihal raporu için metni teslimden önce kontrol ettirin."],
    },
    "odev": {
        "name": "Ödev / Dönem Ödevi", "category": "Eğitim", "icon": "",
        "desc": "Kapak bilgileri, giriş-gelişme-sonuç ve kaynakçayla düzenli bir ödev.",
        "fields": ["title", "author", "student_no", "course", "instructor", "institution", "date"],
        "citation": True, "cover": True,
        "sections": [
            ("Giriş", 1, "Konuyu tanıtın, neden önemli olduğunu ve ödevde neleri ele alacağınızı söyleyin."),
            ("Konunun Ana Hatları", 1, "Konuyu alt başlıklara bölerek açıklayın; her alt başlıkta örnek verin."),
            ("Değerlendirme", 1, "Kendi yorumunuz: güçlü/zayıf yönler, karşılaştırma, eleştiri."),
            ("Sonuç", 1, "Ana fikirleri toparlayın; yeni bilgi eklemeyin."),
            ("Kaynakça", 1, "Kullandığınız kitap, makale ve web kaynakları."),
        ],
        "tips": ["İstenen sayfa/sözcük sınırını durum çubuğundaki sözcük sayısıyla kontrol edin.",
                 "Alıntıları tırnak içinde verin ve kaynağını mutlaka belirtin.",
                 "Teslimden önce F7 ile yazım denetimi yapın."],
    },
    "lab": {
        "name": "Laboratuvar / Deney Raporu", "category": "Eğitim", "icon": "",
        "desc": "Deneyin amacı, kuramı, yapılışı, veriler ve sonuç yorumu.",
        "fields": ["title", "author", "student_no", "course", "date"], "citation": True, "cover": True,
        "sections": [
            ("Deneyin Amacı", 1, "Deneyle neyi ölçmek/göstermek istediğinizi bir iki cümleyle yazın."),
            ("Teorik Bilgi", 1, "Deneyin dayandığı yasa ve formüller."),
            ("Kullanılan Araç ve Gereçler", 1, "Malzeme listesi."),
            ("Deneyin Yapılışı", 1, "Adımları sırayla, geçmiş zamanda yazın."),
            ("Veriler ve Hesaplamalar", 1, "Ölçümleri tabloyla verin; bir örnek hesaplamayı gösterin."),
            ("Sonuç ve Yorum", 1, "Teorik değerle karşılaştırın, hata payını ve kaynaklarını tartışın."),
            ("Kaynakça", 1, "Kullanılan föy, kitap ve kaynaklar."),
        ],
        "tips": ["Birimleri her ölçümde yazın (SI).", "Yüzde hata = |deneysel − teorik| / teorik × 100."],
    },
    "proje": {
        "name": "Proje Önerisi", "category": "Akademik", "icon": "",
        "desc": "TÜBİTAK/BAP benzeri proje başvurusu: amaç, özgün değer, yöntem, iş planı, bütçe.",
        "fields": ["title", "author", "institution", "date", "keywords"], "citation": True, "toc": True,
        "sections": [
            ("Özet", 1, "Projenin amacı, yöntemi ve beklenen çıktıları (en fazla 1 sayfa)."),
            ("Amaç ve Hedefler", 1, "Ölçülebilir, ulaşılabilir hedefler."),
            ("Konu, Kapsam ve Özgün Değer", 1, "Problemin önemi ve projenin literatüre/uygulamaya katkısı."),
            ("Yöntem", 1, "Hedeflere ulaşmak için izlenecek yol; her iş paketi için."),
            ("İş-Zaman Çizelgesi", 1, "İş paketleri ve aylar (aşağıdaki tabloyu doldurun)."),
            ("Bütçe ve Gerekçesi", 1, "Kalem kalem bütçe ve neden gerektiği."),
            ("Risk Yönetimi", 1, "Olası riskler ve B planları."),
            ("Yaygın Etki", 1, "Beklenen bilimsel, ekonomik ve toplumsal çıktılar."),
            ("Kaynakça", 1, "Atıf yapılan kaynaklar."),
        ],
        "tips": ["Hedefleri 'X'i Y yöntemiyle Z düzeyinde ölçmek' gibi somut yazın.",
                 "Değerlendiriciler özgün değer ve yöntem uyumuna en çok puan verir."],
    },
    "literatur": {
        "name": "Literatür Taraması / Derleme", "category": "Akademik", "icon": "",
        "desc": "Bir konudaki çalışmaları sistematik biçimde özetleyen ve eleştiren derleme.",
        "fields": ["title", "author", "institution", "keywords"], "citation": True,
        "sections": [
            ("Özet", 1, "Derlemenin kapsamı, tarama yöntemi ve ana çıkarımlar."),
            ("Giriş", 1, "Konunun önemi ve derlemenin amacı."),
            ("Tarama Yöntemi", 1, "Veri tabanları, anahtar kelimeler, tarih aralığı, dahil etme/dışlama ölçütleri."),
            ("Temalar ve Bulgular", 1, "Çalışmaları temalara göre gruplayıp karşılaştırın."),
            ("Tartışma", 1, "Ortak sonuçlar, çelişkiler ve literatürdeki boşluklar."),
            ("Sonuç", 1, "Gelecek araştırmalar için öneriler."),
            ("Kaynakça", 1, "İncelenen tüm çalışmalar."),
        ],
        "tips": ["Çalışmaları tek tek özetlemek yerine temalar altında sentezleyin.",
                 "Bir özet tablosu (yazar, yıl, örneklem, bulgu) okuru çok rahatlatır."],
    },
    "deneme": {
        "name": "Deneme / Kompozisyon (Essay)", "category": "Eğitim", "icon": "",
        "desc": "Tez cümlesi, destekleyici paragraflar ve sonuçtan oluşan klasik deneme yapısı.",
        "fields": ["title", "author", "course", "date"], "citation": False,
        "sections": [
            ("Giriş", 1, "Dikkat çekici bir açılış ve paragrafın sonunda tez cümleniz (ana iddianız)."),
            ("Birinci Destekleyici Görüş", 2, "Konu cümlesi + kanıt/örnek + tezle bağlantı."),
            ("İkinci Destekleyici Görüş", 2, "Farklı bir açıdan ikinci gerekçe."),
            ("Karşı Görüş ve Yanıtı", 2, "Olası itirazı adil biçimde sunup yanıtlayın."),
            ("Sonuç", 1, "Tezi farklı sözcüklerle yeniden vurgulayın ve düşündürücü bir kapanış yapın."),
        ],
        "tips": ["Her paragraf tek bir fikri savunsun.", "Geçiş ifadeleri kullanın: 'Bunun yanı sıra', 'Öte yandan'."],
    },
    "rapor": {
        "name": "İş / Faaliyet Raporu", "category": "İş ve Resmî", "icon": "",
        "desc": "Yönetici özeti, bulgular, tablo ve önerilerle kurumsal rapor.",
        "fields": ["title", "author", "institution", "date"], "citation": False, "toc": True,
        "sections": [
            ("Yönetici Özeti", 1, "Okuru en çok ilgilendiren 3–5 sonuç ve öneri; yarım sayfa."),
            ("Giriş ve Kapsam", 1, "Raporun amacı, dönemi ve kapsamı."),
            ("Bulgular", 1, "Rakamlarla desteklenmiş durum tespiti."),
            ("Değerlendirme", 1, "Bulguların anlamı ve nedenleri."),
            ("Öneriler", 1, "Somut, sorumlusu ve tarihi belli eylemler."),
        ],
        "tips": ["Yönetici özetini en son yazın.", "Her öneriye bir sorumlu ve tarih atayın."],
    },
    "dilekce": {
        "name": "Dilekçe", "category": "İş ve Resmî", "icon": "",
        "desc": "Resmî kurumlara yazılan, standart düzende dilekçe.",
        "fields": ["recipient", "subject", "author", "date"], "citation": False, "special": "dilekce",
        "sections": [],
        "tips": ["Kurum adı ortalı ve büyük harfle yazılır; altında birimi.",
                 "Son cümle genellikle 'Gereğini bilgilerinize arz ederim.' olur.",
                 "Islak imza için ad soyadın üstünde boşluk bırakın; ekleri 'Ekler:' başlığıyla listeleyin."],
    },
    "mektup": {
        "name": "Resmî / İş Mektubu", "category": "İş ve Resmî", "icon": "",
        "desc": "Gönderen, alıcı, konu ve gövdeden oluşan iş mektubu.",
        "fields": ["author", "recipient", "subject", "date"], "citation": False, "template": "Mektup", "sections": [],
        "tips": ["İlk paragrafta yazma amacınızı açıkça belirtin.", "Kısa ve nazik bir kapanış yapın."],
    },
    "toplanti": {
        "name": "Toplantı Notları", "category": "İş ve Resmî", "icon": "",
        "desc": "Katılımcılar, gündem, kararlar ve yapılacaklar tablosu.",
        "fields": ["title", "date"], "citation": False, "template": "Toplantı notları", "sections": [],
        "tips": ["Her kararın sorumlusunu ve son tarihini yazın."],
    },
    "ozgecmis": {
        "name": "Özgeçmiş (CV)", "category": "Kişisel", "icon": "",
        "desc": "Özet, deneyim, eğitim ve beceriler bölümlü özgeçmiş.",
        "fields": ["author"], "citation": False, "template": "Özgeçmiş", "sections": [],
        "tips": ["Deneyimleri yeniden eskiye sıralayın.", "Başarıları sayılarla anlatın (%20 artış gibi).",
                 "Tek sayfa hedefleyin."],
    },
    "bos": {
        "name": "Boş Belge", "category": "Kişisel", "icon": "",
        "desc": "Temiz bir sayfa. Rehber yine de genel yazım ipuçları verir.",
        "fields": [], "citation": False, "sections": [], "tips": [],
    },
}

# Bölüm adına göre rehber: (anahtar sözcükler, ipuçları, örnek ifadeler)
SECTION_GUIDE = [
    (("özet", "abstract", "yönetici özeti"),
     ["Amaç → Yöntem → Bulgular → Sonuç sırasını izleyin.", "Kaynak, kısaltma ve tablo kullanmayın.",
      "Genellikle 150–250 sözcük; tek paragraf."],
     ["Bu çalışmanın amacı, … ile … arasındaki ilişkiyi incelemektir.",
      "Araştırmada … desenli bir yöntem kullanılmış ve … katılımcıdan veri toplanmıştır.",
      "Bulgular, … değişkeninin … üzerinde anlamlı bir etkisi olduğunu göstermektedir.",
      "Sonuç olarak, … önerilmektedir."]),
    (("anahtar",),
     ["3–5 kavram yazın; başlıkta geçenleri tekrar etmemeye çalışın.", "Virgülle ayırın."],
     ["Anahtar Kelimeler: …, …, …"]),
    (("giriş", "introduction"),
     ["Genelden özele ilerleyin: konu → önem → literatürdeki boşluk → amaç.",
      "Son paragrafta araştırma sorusunu veya hipotezi açıkça yazın."],
     ["Son yıllarda … konusu giderek artan bir ilgi görmektedir.",
      "Ancak literatürde … konusunda sınırlı sayıda çalışma bulunmaktadır.",
      "Bu boşluktan hareketle, bu çalışmada şu sorulara yanıt aranmıştır:",
      "Bu araştırmanın temel amacı … belirlemektir."]),
    (("literatür", "kuramsal", "kavramsal", "ilgili araştırma", "çerçeve"),
     ["Çalışmaları tek tek değil, ortak temalar altında karşılaştırarak anlatın.",
      "Her paragrafı sizin çalışmanıza bağlayan bir cümleyle bitirin."],
     ["… (Yazar, Yıl) tarafından yapılan çalışmada … bulunmuştur.",
      "Benzer şekilde, … de … sonucuna ulaşmıştır.",
      "Bu bulguların aksine, … farklı bir sonuç rapor etmiştir.",
      "Bu çalışmalar birlikte değerlendirildiğinde … görülmektedir."]),
    (("yöntem", "method", "materyal", "deneyin yapılışı", "evren", "örneklem", "veri toplama", "analiz"),
     ["Başka bir araştırmacının çalışmayı tekrarlayabileceği ayrıntıda yazın.",
      "Geçmiş zaman ve edilgen çatı kullanılır ('toplanmıştır', 'analiz edilmiştir')."],
     ["Araştırmada … modeli kullanılmıştır.",
      "Araştırmanın örneklemini, … yöntemiyle seçilen … kişi oluşturmaktadır.",
      "Veriler, … tarafından geliştirilen … ölçeği ile toplanmıştır.",
      "Verilerin analizinde … testi kullanılmış, anlamlılık düzeyi .05 olarak alınmıştır."]),
    (("bulgu", "results", "veriler", "temalar"),
     ["Yorum katmayın; yalnızca ne bulduğunuzu yazın.", "Her tablo/şekilden önce metinde ona atıf yapın."],
     ["Tablo 1'de görüldüğü gibi, …",
      "Gruplar arasında istatistiksel olarak anlamlı bir fark bulunmuştur (p < .05).",
      "Katılımcıların büyük çoğunluğu (%…) … belirtmiştir.",
      "… ile … arasında pozitif yönde orta düzeyde bir ilişki saptanmıştır (r = .…)."]),
    (("tartışma", "değerlendirme", "discussion", "yorum"),
     ["Bulguları literatürle karşılaştırın: destekleyen ve çelişen çalışmalar.",
      "Beklenmeyen sonuçlar için olası açıklamalar sunun; sınırlılıkları dürüstçe belirtin."],
     ["Bu bulgu, … (Yıl) çalışmasının sonuçlarıyla örtüşmektedir.",
      "Bu farklılığın nedeni … olabilir.",
      "Bu çalışmanın bazı sınırlılıkları bulunmaktadır: …",
      "Elde edilen bulgular, … açısından önemli ipuçları sunmaktadır."]),
    (("sonuç", "conclusion", "öneri"),
     ["Yeni bilgi eklemeyin; ana çıkarımı net bir cümleyle söyleyin.",
      "Önerileri uygulayıcılara ve araştırmacılara ayrı ayrı yazın."],
     ["Sonuç olarak, bu çalışma … olduğunu ortaya koymuştur.",
      "Gelecek çalışmalarda … ele alınması önerilmektedir.",
      "Uygulayıcıların … konusuna dikkat etmesi yararlı olacaktır."]),
    (("kaynak", "references", "bibliyografya"),
     ["Metinde atıf yapılan her kaynak burada, burada olan her kaynak metinde olmalı.",
      "Rehber panelindeki 'Kaynak ekle' ile seçtiğiniz stilde otomatik biçimlendirebilirsiniz."],
     []),
    (("önsöz", "teşekkür"),
     ["Danışmanınıza, jüriye ve destek olanlara teşekkür edin; 1 sayfayı geçmeyin."],
     ["Bu tezin hazırlanmasında değerli katkılarını esirgemeyen danışmanım … teşekkür ederim."]),
]

GENERAL_TIPS = [
    "Başlıkları Stiller'den (Başlık 1/2/3) seçin: içindekiler ve gezinti bölmesi bunlardan oluşur.",
    "Köşeli parantezli gri metinler yer tutucudur; tıklayınca seçilir, yazmaya başlayınca kaybolur.",
    "Ctrl+Alt+M ile seçili metne açıklama, Ctrl+Alt+F ile dipnot ekleyin.",
    "Belgeyi sık sık Ctrl+S ile kaydedin; OmOffice ayrıca 30 saniyede bir kurtarma kopyası alır.",
]

PHRASE_BANK = {
    "Amaç belirtme": ["Bu çalışmanın amacı …", "Bu araştırmada … incelenmiştir.", "Çalışmada şu sorulara yanıt aranmıştır:"],
    "Literatüre atıf": ["… (Yazar, Yıl) belirttiği gibi, …", "Alanyazında … konusunda görüş birliği vardır.",
                        "Önceki çalışmalar … göstermiştir (Yazar, Yıl; Yazar, Yıl)."],
    "Karşılaştırma": ["Buna karşın, …", "Benzer biçimde, …", "… aksine, …", "Her iki çalışmada da …"],
    "Bulgu sunma": ["Analiz sonuçları … göstermektedir.", "Tablo …'de görüldüğü gibi …", "Anlamlı bir fark bulunmamıştır."],
    "Sınırlılık": ["Bu çalışma … ile sınırlıdır.", "Bulguların genellenmesinde dikkatli olunmalıdır çünkü …"],
    "Sonuç bağlama": ["Sonuç olarak, …", "Özetle, …", "Bu bulgular ışığında …"],
    "Geçiş ifadeleri": ["Bunun yanı sıra, …", "Öte yandan, …", "Dolayısıyla, …", "Bu nedenle, …", "Ayrıca, …"],
}

CITATION_STYLES = ["APA 7", "IEEE", "MLA 9"]
REF_TYPES = ["Dergi makalesi", "Kitap", "Web sayfası"]


def match_section(heading):
    h = turkish_lower(re.sub(r"^[\d.\s]+", "", heading or "")).strip()
    for keys, tips, examples in SECTION_GUIDE:
        if any(k in h for k in keys):
            return tips, examples
    return None, None


def _authors(raw):
    """'Yılmaz, A.; Demir, B. C.' biçimindeki yazar listesini [(soyad, adlar)] yapar."""
    out = []
    for part in re.split(r";|\s+ve\s+|\s+and\s+", raw or ""):
        part = part.strip()
        if not part:
            continue
        if "," in part:
            last, first = [x.strip() for x in part.split(",", 1)]
        else:
            bits = part.split()
            last, first = bits[-1], " ".join(bits[:-1])
        out.append((last, first))
    return out


def _initials(first):
    return " ".join(f"{p[0]}." for p in re.split(r"[\s.]+", first) if p)


def format_reference(style, r):
    """r: dict(type, authors, year, title, source, volume, issue, pages, publisher, url, doi, accessed)."""
    au = _authors(r.get("authors"))
    year = r.get("year") or "t.y."
    title = (r.get("title") or "").strip().rstrip(".")
    src = (r.get("source") or "").strip()
    vol, iss, pages = r.get("volume", ""), r.get("issue", ""), r.get("pages", "")
    doi = (r.get("doi") or "").strip()
    url = (r.get("url") or "").strip()
    link = f"https://doi.org/{doi}" if doi and not doi.startswith("http") else (doi or url)
    kind = r.get("type", REF_TYPES[0])
    if style.startswith("APA"):
        names = [f"{l}, {_initials(f)}".strip(", ") for l, f in au]
        if len(names) > 1:
            names_s = ", ".join(names[:-1]) + ", & " + names[-1]
        else:
            names_s = names[0] if names else ""
        if kind == "Kitap":
            s = f"{names_s} ({year}). *{title}*. {r.get('publisher', '')}."
        elif kind == "Web sayfası":
            s = f"{names_s} ({year}). *{title}*. {src}. {url}"
        else:
            v = f", *{vol}*" if vol else ""
            i = f"({iss})" if iss else ""
            pg = f", {pages}" if pages else ""
            s = f"{names_s} ({year}). {title}. *{src}*{v}{i}{pg}."
            if link:
                s += f" {link}"
        return s.strip()
    if style.startswith("IEEE"):
        names = [f"{_initials(f)} {l}".strip() for l, f in au]
        names_s = ", ".join(names[:-1]) + (", and " if len(names) > 2 else " and ") + names[-1] \
            if len(names) > 1 else (names[0] if names else "")
        if kind == "Kitap":
            return f"{names_s}, *{title}*. {r.get('publisher', '')}, {year}."
        if kind == "Web sayfası":
            acc = f" (erişim: {r['accessed']})" if r.get("accessed") else ""
            return f"{names_s}, \"{title},\" {src}. [Çevrimiçi]. Erişim: {url}{acc}"
        parts = [f"{names_s}, \"{title},\" *{src}*"]
        if vol:
            parts.append(f"cilt {vol}")
        if iss:
            parts.append(f"sayı {iss}")
        if pages:
            parts.append(f"ss. {pages}")
        parts.append(str(year))
        s = ", ".join(parts) + "."
        return s + (f" doi: {doi}." if doi else "")
    # MLA 9
    if au:
        l, f = au[0]
        names_s = f"{l}, {f}"
        if len(au) == 2:
            names_s += f", and {au[1][1]} {au[1][0]}"
        elif len(au) > 2:
            names_s += ", et al"
    else:
        names_s = ""
    if kind == "Kitap":
        return f"{names_s}. *{title}*. {r.get('publisher', '')}, {year}."
    if kind == "Web sayfası":
        return f"{names_s}. \"{title}.\" *{src}*, {year}, {url}."
    bits = [f"{names_s}. \"{title}.\" *{src}*"]
    if vol:
        bits.append(f"vol. {vol}")
    if iss:
        bits.append(f"no. {iss}")
    bits.append(str(year))
    if pages:
        bits.append(f"pp. {pages}")
    return ", ".join(bits) + "."


def in_text(style, r, number):
    au = _authors(r.get("authors"))
    year = r.get("year") or "t.y."
    if style.startswith("IEEE"):
        return f"[{number}]"
    if not au:
        return f"({(r.get('title') or '')[:20]}, {year})"
    if style.startswith("APA"):
        if len(au) == 1:
            who = au[0][0]
        elif len(au) == 2:
            who = f"{au[0][0]} & {au[1][0]}"
        else:
            who = f"{au[0][0]} vd."
        return f"({who}, {year})"
    who = au[0][0] if len(au) < 3 else f"{au[0][0]} vd."
    if len(au) == 2:
        who = f"{au[0][0]} ve {au[1][0]}"
    pages = r.get("pages", "")
    return f"({who}{' ' + pages.split('-')[0] if pages else ''})"
