import os
import re

from chardet.universaldetector import UniversalDetector
from pymarc import MARCReader
from app.models import Record, Author, Keyword, \
    SourceDatabase, DocumentType, Publisher
from app import db
from flask import current_app
from pathlib import Path

DOCUMENT_TYPES = {
    'a': 'Статьи, периодика',
    'b': 'Часть сериального ресурса',
    'c': 'Собрание (коллекция, подборка)',
    'd': 'Часть собрания (коллекции, подборки)',
    'i': 'Интегрируемый ресурс',
    'm': 'Монографический ресурс',
    's': 'Сериальный ресурс'
}
HASH_FILE = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..', 'hashes.txt'))
file = Path(HASH_FILE)
file.touch(exist_ok=True)
ENCODING_TYPES = ['cp1251', 'utf-8']



# Get file encoding type
def get_encoding_type(file):
    data = open(file, 'rb')
    detector = UniversalDetector()
    for line in data.readlines():
        res = detector.result['encoding']
        detector.feed(line)
        if detector.done:
            break
    detector.close()
    data.close()
    return detector.result['encoding']



def bpow(a, n, mod):
    res = 1
    while n:
        if n & 1:
            res = (res * a) % mod
        a = (a * a) % mod
        n >>= 1
    return res


class DBLoader:
    N = 1000
    p = 199
    mod = 1e9 + 9
    P = []

    @classmethod
    def _probe_encoding_types(cls, file):
        for encoding in ENCODING_TYPES:
            with open(file, 'rb') as fh:
                reader = MARCReader(fh, file_encoding=encoding)
                for record in reader:
                    if record is None:
                        break
                    else:
                        file_encoding = encoding
                        break
        return file_encoding

    @classmethod
    def _get_metadata(cls, input_data):
        marc_file = os.path.join(current_app.config['UPLOAD_FOLDER'], input_data)
        # Get file encoding
        file_encoding = cls._probe_encoding_types(marc_file)
        # Get source database once
        with open(marc_file, 'rb') as fh:
            reader = MARCReader(fh, file_encoding=file_encoding)
            for record in reader:
                if record['801'] is not None:
                    if record['801']['b'] is not None:
                        source_database_name = record['801']['b']
                        break
                elif record['040'] is not None:
                    if record['040']['a'] is not None:
                        source_database_name = record['040']['a']
                        break
        return source_database_name, file_encoding

    @classmethod
    def _gen_p(cls):
        for i in range(0, cls.N, 1):
            cls.P.append(bpow(cls.p, i, cls.mod))

    @classmethod
    def _hash(cls, s):
        s_hash = 0
        if len(cls.P) == 0:
            cls._gen_p()

        for i in range(0, len(s), 1):
            s_hash += (ord(s[i]) * cls.P[i]) % cls.mod

        return int(s_hash)

    @classmethod
    def _load_tree(cls):
        a_tree = set()
        file = open(HASH_FILE, 'r')
        for line in file:
            a_tree.add(int(line))
        return a_tree

    @classmethod
    def _save_tree(cls, a_tree):
        f = open(HASH_FILE, 'w+')
        for node in a_tree:
            f.write(str(node) + '\n')
        f.close()

    @staticmethod
    def _empty_directory(directory):
        for f in os.listdir(directory):
            os.remove(os.path.join(directory, f))

    @classmethod
    def _process_rusmarc(cls, input_data):
        marc_file = os.path.join(current_app.config['UPLOAD_FOLDER'], input_data)
        source_database_name, file_encoding = cls._get_metadata(marc_file)
        source_database_entry = db.session.query(SourceDatabase).filter_by(name=source_database_name).scalar()
        if source_database_entry is None:
            source_database_entry = SourceDatabase(name=source_database_name)

        a_tree = cls._load_tree()
        with open(marc_file, 'rb') as fh:
            reader = MARCReader(fh, file_encoding=file_encoding)
            for record in reader:
                record_string = ''
                record_string += source_database_entry.name
                record_table = Record()
                # Title
                if record['200'] is not None:
                    if record['200']['a'] is not None:
                        record_table.title = record['200']['a']
                        record_string += record_table.title

                # Document type
                document_type_entry = db.session.query(DocumentType).filter_by(
                    name=DOCUMENT_TYPES.get(record.leader[7])).scalar()
                if document_type_entry is not None:
                    record_string += document_type_entry.name
                else:
                    document_type_entry = DocumentType(name=DOCUMENT_TYPES.get(record.leader[7]))
                    record_string += document_type_entry.name

                # Publishing year
                if record['210'] is not None:
                    if record['210']['d'] is not None:
                        record_table.publishing_year = int(record['210']['d'])
                        record_string += record['210']['d']

                # URL
                if record['856'] is not None:
                    if record['856']['u'] is not None:
                        record_table.url = record['856']['u']
                        record_string += record['856']['u']

                _hash = cls._hash(record_string)
                if _hash not in a_tree:
                    a_tree.add(_hash)
                    db.session.add(document_type_entry)
                    db.session.add(source_database_entry)
                    record_table.document_type.append(document_type_entry)
                    record_table.source_database.append(source_database_entry)
                else:
                    continue

                # Description
                if record['330'] is not None:
                    if record['330']['a'] is not None:
                        record_table.description = record['330']['a']

                # Cover
                if record['953'] is not None:
                    if record['953']['a'] is not None:
                        record_table.cover = record['953']['a']
                elif record['956'] is not None:
                    if record['956']['a'] is not None:
                        record_table.cover = record['956']['a']

                # ISBN
                if record['010'] is not None:
                    if record['010']['a'] is not None:
                        record_table.isbn = re.sub('\D', '', record['010']['a'])

                # ISSN
                if record['011'] is not None:
                    if record['011']['a'] is not None:
                        record_table.issn = re.sub('\D', '', record['011']['a'])

                # Pages
                if record['215'] is not None:
                    if record['215']['a'] is not None:
                        temp = re.findall(r'\d+', str(record['215']['a']))
                        record_table.pages = int(temp[0])

                # UDC
                if record['675'] is not None:
                    if record['675']['a'] is not None:
                        record_table.udc = str(record['675']['a'])

                # BBK
                if record['686'] is not None:
                    if record['686']['a'] is not None:
                        record_table.bbk = str(record['686']['a'])

                # Authors
                if record['700'] is not None:
                    if record['700']['a'] is not None:
                        if record['700']['b'] is not None:
                            author_entry = db.session.query(Author).filter_by(
                                name=record['700']['a'] + ' ' + record['700']['b']).scalar()
                            if author_entry is not None:
                                record_table.authors.append(author_entry)
                                db.session.add(author_entry)
                            else:
                                author_entry = Author(name=record['700']['a'] + ' ' + record['700']['b'])
                                record_table.authors.append(author_entry)
                                db.session.add(author_entry)
                        elif record['700']['g'] is not None:
                            initials = record['700']['g'].split()
                            for i in range(len(initials)):
                                initials[i] = initials[i][0] + '.'
                            initials = ' '.join([str(item) for item in initials])
                            author_entry = db.session.query(Author).filter_by(
                                name=record['700']['a'] + ' ' + initials).scalar()
                            if author_entry is not None:
                                record_table.authors.append(author_entry)
                                db.session.add(author_entry)
                            else:
                                author_entry = Author(name=record['700']['a'] + ' ' + initials)
                                record_table.authors.append(author_entry)
                                db.session.add(author_entry)
                if record['701'] is not None:
                    if record['701']['a'] is not None:
                        if record['701']['b'] is not None:
                            authors_list = []
                            for f in record.get_fields('701'):
                                if f['a'] is not None and f['b'] is not None:
                                    authors_list.append(f['a'] + ' ' + f['b'])
                            for val in authors_list:
                                author_entry = db.session.query(Author).filter_by(name=val).scalar()
                                if author_entry is not None:
                                    record_table.authors.append(author_entry)
                                    db.session.add(author_entry)
                                else:
                                    author_entry = Author(name=val)
                                    record_table.authors.append(author_entry)
                                    db.session.add(author_entry)
                        elif record['701']['a'] is not None:
                            if record['701']['g'] is not None:
                                authors_list = []
                                for f in record.get_fields('701'):
                                    if f['a'] is not None and f['g'] is not None:
                                        initials = f['g'].split()
                                        for i in range(len(initials)):
                                            initials[i] = initials[i][0] + '.'
                                        initials = ' '.join([str(item) for item in initials])
                                        authors_list.append(f['a'] + ' ' + initials)
                                for val in authors_list:
                                    author_entry = db.session.query(Author).filter_by(name=val).scalar()
                                    if author_entry is not None:
                                        record_table.authors.append(author_entry)
                                        db.session.add(author_entry)
                                    else:
                                        author_entry = Author(name=val)
                                        record_table.authors.append(author_entry)
                                        db.session.add(author_entry)
                if record['702'] is not None:
                    if record['702']['a'] is not None and record['702']['b'] is not None:
                        authors_list = []
                        for f in record.get_fields('702'):
                            if f['a'] is not None and f['b'] is not None:
                                authors_list.append(f['a'] + ' ' + f['b'])
                        for val in authors_list:
                            author_entry = db.session.query(Author).filter_by(name=val).scalar()
                            if author_entry is not None:
                                record_table.authors.append(author_entry)
                                db.session.add(author_entry)
                            else:
                                author_entry = Author(name=val)
                                record_table.authors.append(author_entry)
                                db.session.add(author_entry)
                    elif record['702']['a'] is not None:
                        if record['702']['g'] is not None:
                            authors_list = []
                            for f in record.get_fields('702'):
                                if f['a'] is not None and f['g'] is not None:
                                    initials = f['g'].split()
                                for i in range(len(initials)):
                                    initials[i] = initials[i][0] + '.'
                                initials = ' '.join([str(item) for item in initials])
                                authors_list.append(f['a'] + ' ' + initials)
                            for val in authors_list:
                                author_entry = db.session.query(Author).filter_by(name=val).scalar()
                                if author_entry is not None:
                                    record_table.authors.append(author_entry)
                                    db.session.add(author_entry)
                                else:
                                    author_entry = Author(name=val)
                                    record_table.authors.append(author_entry)
                                    db.session.add(author_entry)

                # Publisher
                if record['210'] is not None:
                    if record['210']['c'] is not None:
                        publisher_entry = db.session.query(Publisher).filter_by(name=record['210']['c']).scalar()
                        if publisher_entry is not None:
                            db.session.add(publisher_entry)
                            record_table.publisher.append(publisher_entry)
                        else:
                            publisher_entry = Publisher(name=record['210']['c'])
                            record_table.publisher.append(publisher_entry)
                            db.session.add(publisher_entry)
                # Keywords
                if record['610'] is not None:
                    if record['610']['a'] is not None:
                        keywords_list = []
                        for f in record.get_fields('610'):
                            keywords_list.append(f['a'].lower())
                        for val in keywords_list:
                            temp = []
                            if '--' in val:
                                temp = val.split('--')
                                keywords_list.remove(val)
                            if ',' in val:
                                temp = val.split(',')
                                keywords_list.remove(val)
                            for val1 in temp:
                                if val1 != ' ' and val1 != '':
                                    keywords_list.append(val1.strip())
                        keywords_list = list(set(keywords_list))
                        for val in keywords_list:
                            val = val.replace('"', '')
                            keyword_entry = db.session.query(Keyword).filter_by(name=val).scalar()
                            if keyword_entry is not None:
                                record_table.keywords.append(keyword_entry)
                                db.session.add(keyword_entry)
                            else:
                                keyword_entry = Keyword(name=val)
                                record_table.keywords.append(keyword_entry)
                                db.session.add(keyword_entry)

                # TODO: generate bibliographic description
                record_table.bibliographic_description = None
                db.session.add(record_table)
        cls._save_tree(a_tree)

    @classmethod
    def _process_marc21(cls, input_data):
        marc_file = os.path.join(current_app.config['UPLOAD_FOLDER'], input_data)
        source_database_name, file_encoding = cls._get_metadata(marc_file)
        source_database_entry = db.session.query(SourceDatabase).filter_by(name=source_database_name).scalar()
        if source_database_entry is None:
            source_database_entry = SourceDatabase(name=source_database_name)

        a_tree = cls._load_tree()
        with open(marc_file, 'rb') as fh:
            reader = MARCReader(fh, file_encoding=file_encoding)
            for record in reader:
                record_string = ''
                record_string += source_database_entry.name
                record_table = Record()
                # Title
                if record.title() is not None:
                    record_table.title = record.title()
                    record_string += record.title()

                # Document type
                document_type_entry = db.session.query(DocumentType).filter_by(
                    name=DOCUMENT_TYPES.get(record.leader[7])).scalar()
                if document_type_entry is not None:
                    record_string += document_type_entry.name
                else:
                    document_type_entry = DocumentType(name=DOCUMENT_TYPES.get(record.leader[7]))
                    record_string += document_type_entry.name

                # Publishing year
                if record['260'] is not None:
                    if record['260']['c'] is not None:
                        record_table.publishing_year = record['260']['c']
                        record_string += str(record['260']['c'])

                # URL
                if record['856'] is not None:
                    if record['856']['u'] is not None:
                        record_table.url = record['856']['u']
                        record_string += record['856']['u']
                elif record['003'] is not None:
                    record_table.url = record['003']
                    record_string += record['003']

                _hash = cls._hash(record_string)
                if _hash not in a_tree:
                    a_tree.add(_hash)
                    db.session.add(document_type_entry)
                    db.session.add(source_database_entry)
                    record_table.hash = _hash
                    record_table.document_type.append(document_type_entry)
                    record_table.source_database.append(source_database_entry)
                else:
                    continue

                # Description
                if record['520'] is not None:
                    if record['520']['a'] is not None:
                        record_table.description = str(record['520']['a'])

                # Cover
                if record['856'] is not None:
                    if record['856']['x'] is not None:
                        record_table.cover = record['856']['x']

                # ISBN
                if record.isbn() is not None:
                    record_table.isbn = record.isbn()

                # ISSN
                if record.issn() is not None:
                    record_table.issn = record.issn()

                # Pages
                if record['300'] is not None:
                    if record['300']['a'] is not None:
                        temp = re.findall(r'\d+', str(record['300']['a']))
                        record_table.pages = int(temp[0])

                # UDC
                if record['080'] is not None:
                    if record['080']['a'] is not None:
                        record_table.udc = str(record['080']['a'])

                # BBK
                if record['084'] is not None:
                    if record['084']['a'] is not None:
                        record_table.bbk = record['084']['a']

                # Authors
                if record['100'] is not None:
                    if record['100']['a'] is not None:
                        author_entry = db.session.query(Author).filter_by(name=record['100']['a']).scalar()
                        if author_entry is not None:
                            record_table.authors.append(author_entry)
                            db.session.add(author_entry)
                        else:
                            author_entry = Author(name=record['100']['a'])
                            record_table.authors.append(author_entry)
                            db.session.add(author_entry)
                if record['700'] is not None:
                    if record['700']['a'] is not None:
                        authors_list = []
                        for f in record.get_fields('700'):
                            authors_list.append(f['a'])
                        for val in authors_list:
                            author_entry = db.session.query(Author).filter_by(name=val).scalar()
                            if author_entry is not None:
                                record_table.authors.append(author_entry)
                                db.session.add(author_entry)
                            else:
                                author_entry = Author(name=val)
                                record_table.authors.append(author_entry)
                                db.session.add(author_entry)

                # Publisher
                if record['260'] is not None:
                    if record['260']['b'] is not None:
                        publisher_entry = db.session.query(Publisher).filter_by(name=record.publisher()).scalar()
                        if publisher_entry is not None:
                            db.session.add(publisher_entry)
                            record_table.publisher.append(publisher_entry)
                        else:
                            publisher_entry = Publisher(name=record.publisher())
                            record_table.publisher.append(publisher_entry)
                            db.session.add(publisher_entry)

                # Keywords
                if record['653'] is not None:
                    if record['653']['a'] is not None:
                        keywords_list = []
                        for f in record.get_fields('653'):
                            keywords_list.append(f['a'].lower())
                        for val in keywords_list:
                            temp = []
                            if '--' in val:
                                temp = val.split('--')
                                keywords_list.remove(val)
                            if ',' in val:
                                temp = val.split(',')
                                keywords_list.remove(val)
                            for val1 in temp:
                                if val1 != ' ' and val1 != '':
                                    keywords_list.append(val1.strip())
                        keywords_list = list(set(keywords_list))
                        for val in keywords_list:
                            val = val.replace('"', '')
                            keyword_entry = db.session.query(Keyword).filter_by(name=val).scalar()
                            if keyword_entry is not None:
                                record_table.keywords.append(keyword_entry)
                                db.session.add(keyword_entry)
                            else:
                                keyword_entry = Keyword(name=val)
                                record_table.keywords.append(keyword_entry)
                                db.session.add(keyword_entry)

                # TODO: generate bibliographic description
                record_table.bibliographic_description = None
                db.session.add(record_table)
        cls._save_tree(a_tree)

    @classmethod
    def upload_to_database(cls):
        directory = str(current_app.config['UPLOAD_FOLDER'])
        for filename in os.listdir(directory):
            f = os.path.join(directory, filename)
            source_db_name = cls._get_metadata(filename)[0]
            if source_db_name == 'Издательство Лань' or source_db_name == 'RUCONT':
                cls._process_rusmarc(filename)
            elif source_db_name == 'ИКО Юрайт':
                cls._process_marc21(filename)
        Record.reindex()
        db.session.commit()
        DBLoader._empty_directory(directory)
