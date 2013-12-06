#!/usr/bin/env python
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  author: terry.yinzhe@gmail.com
#
"""
lizard is a simple code complexity analyzer without caring about the C/C++
header files or Java imports. It can deal with

* Java
* C/C++
* Objective C.

It counts

* the nloc (net lines of code, excluding comments and blanks),
* CCN (cyclomatic complexity number),
* token count of functions.
* parameter count of functions.

You can set limitation for CCN (-C), the number of parameters (-a). Functions
that exceed these limitations will generate warnings. The exit code of lizard
will be none-Zero if there are warnings.

This tool actually calculates how complex the code 'looks' rather than how
complex the code real 'is'. People will need this tool because it's often very
hard to get all the included folders and files right when they are complicated.
But we don't really need that kind of accuracy when come to cyclomatic
complexity.

It requires python2.6 or above (early versions are not verified).
"""

BUG_REPORTING = "please report bug to terry.yinzhe@gmail.com or https://github.com/terryyin/lizard.\n"

VERSION = "0.0.1"
HFCCA_VERSION = "1.7.2"


import itertools, traceback
import re


DEFAULT_CCN_THRESHOLD = 15


'''
The analyzing process
=====================
Source code => Tokens => UniversalCode

UniversalCode.get_statistics => The statistics of one source file.

'''


class FunctionInfo(object):
    '''
    Statistic information of a function.
    '''

    def __init__(self, name, start_line):
        self.cyclomatic_complexity = 1
        self.nloc = 0
        self.token_count = 0
        self.name = name
        self.long_name = name
        self.start_line = start_line
        self.parameter_count = 0

    def add_to_function_name(self, app):
        self.name += app
        self.long_name += app

    def add_to_long_name(self, app):
        self.long_name += app

    def add_parameter(self, token):
        self.add_to_long_name(" " + token)

        if self.parameter_count == 0:
            self.parameter_count = 1
        if token == ",":
            self.parameter_count += 1


class FileInformation(object):
    ''' 
    Statistic information of a source file.
    Including all the functions and the file summary.
    '''

    def __init__(self, filename, nloc, function_list):
        self.filename = filename
        self.nloc = nloc
        self.function_list = function_list

    average_NLOC = property(lambda self:self._functions_average("nloc"))
    average_token = property(lambda self:self._functions_average("token_count"))
    average_CCN = property(lambda self:self._functions_average("cyclomatic_complexity"))
    CCN = property(lambda self:sum(fun.cyclomatic_complexity for fun in self.function_list))

    def _functions_average(self, att):
        return sum(getattr(fun, att) for fun in self.function_list) \
                / len(self.function_list) if self.function_list else 0


class UniversalCode(object):
    """
        UniversalCode is the code that is unrelated to any programming
        languages. The code could be:
        START_NEW_FUNCTION
            ADD_TO_FUNCTION_NAME
            ADD_TO_LONG_FUNCTION_NAME
                PARAMETER
                    CONDITION
                    TOKEN
        END_OF_FUNCTION

        A TokenTranslator will generate UniversalCode.
    """

    def __init__(self):
        self.START_NEW_FUNCTION('', 0)
        self.newline = True
        self.nloc = 0
        self.function_list = []

    def START_NEW_FUNCTION(self, name, start_line):
        self.current_function = FunctionInfo(name, start_line)

    def CONDITION(self):
        self.TOKEN()
        self.current_function.cyclomatic_complexity += 1

    def TOKEN(self):
        if self.newline:
            self.current_function.nloc += 1
            self.newline = False
        self.current_function.token_count += 1

    def NEW_LINE(self):
        self.nloc += 1
        self.newline = True

    def ADD_TO_LONG_FUNCTION_NAME(self, app):
        self.current_function.add_to_long_name(app)

    def ADD_TO_FUNCTION_NAME(self, app):
        self.current_function.add_to_function_name(app)

    def PARAMETER(self, token):
        self.current_function.add_parameter(token)

    def END_OF_FUNCTION(self):
        self.function_list.append(self.current_function)
        self.START_NEW_FUNCTION('', 0)


class ParsingError(Exception):

    def __init__(self, line_number):
        self.line_number = line_number
        self.filename = ''
        self.code = ''

    def __str__(self):
        try:
            line = self.code.splitlines()[self.line_number - 1]
        except:
            line = ''
        return '''!!!Exception Happens!!!
At %s:%d: '%s'
If possible, ''' % (self.filename, self.line_number, line) + BUG_REPORTING


class LanguageReaderBase(object):
    '''
    This is the base class for any programming language reader.
    It reader the tokens of a certain language and generate universal_code
    by calling it's -generate_universal_code- method.

    The derived class should implement a series of 'state' functions. The
    most basic and start state is _GLOBAL. Derived class must implement _GLOBAL
    and other states. When the state changes, simply assign the state method to
    self._state.
    During each state, call the methods of self.universal_code to build the
    universal code.
    '''

    def __init__(self):
        self._state = self._GLOBAL
        self.current_line = 0
        self.univeral_code = UniversalCode()

    def generate_universal_code(self, tokens):
        for token, self.current_line in tokens:
            try:
                if token.isspace():
                    self.univeral_code.NEW_LINE()
                else:
                    self.process_token(token)
            except:
                raise ParsingError(self.current_line)

        return self.univeral_code

    def process_token(self, token):
        return self._state(token)


class CLikeReader(LanguageReaderBase):
    '''
    This is the reader for C, C++ and Java.
    '''

    def __init__(self):
        super(CLikeReader, self).__init__()
        self.conditions = set(
            ['if', 'for', 'while', '&&', '||', 'case', '?', '#if', '#elif', 'catch'])
        self.bracket_level = 0
        self.br_count = 0
        self.last_preprocessor = None

    def remove_hash_if_from_conditions(self):
        self.conditions.remove("#if")
        self.conditions.remove("#elif")

    def _is_condition(self, token):
        return token in self.conditions

    def process_token(self, token):
        if token.startswith("#") and self._state != self._IMP:
            return
        return super(CLikeReader, self).process_token(token)

    def _GLOBAL(self, token):
        if token == '(':
            self.bracket_level += 1
            self._state = self._DEC
            self.univeral_code.ADD_TO_LONG_FUNCTION_NAME(token)
        elif token == '::':
            self._state = self._NAMESPACE
        else:
            self.univeral_code.START_NEW_FUNCTION(token, self.current_line)
            if token == 'operator':
                self._state = self._OPERATOR

    def _OPERATOR(self, token):
        if token != '(':
            self._state = self._GLOBAL
        self.univeral_code.ADD_TO_FUNCTION_NAME(' ' + token)

    def _NAMESPACE(self, token):
        self._state = self._OPERATOR if token == 'operator'  else self._GLOBAL
        self.univeral_code.ADD_TO_FUNCTION_NAME("::" + token)

    def _DEC(self, token):
        if token in ('(', "<"):
            self.bracket_level += 1
        elif token in (')', ">"):
            self.bracket_level -= 1
            if (self.bracket_level == 0):
                self._state = self._DEC_TO_IMP
        elif self.bracket_level == 1:
            self.univeral_code.PARAMETER(token)
            return
        self.univeral_code.ADD_TO_LONG_FUNCTION_NAME(" " + token)

    def _DEC_TO_IMP(self, token):
        if token == 'const':
            self.univeral_code.ADD_TO_LONG_FUNCTION_NAME(" " + token)
        elif token == '{':
            self.br_count += 1
            self._state = self._IMP
        elif token == ":":
            self._state = self._CONSTRUCTOR_INITIALIZATION_LIST
        else:
            self._state = self._GLOBAL

    def _CONSTRUCTOR_INITIALIZATION_LIST(self, token):
        if token == '{':
            self.br_count += 1
            self._state = self._IMP

    def _IMP(self, token):
        if token in ("#else", "#if", "#endif"):
            self.last_preprocessor = token
        # will ignore the braces in a #else branch            
        if self.last_preprocessor != '#else':
            if token == '{':
                self.br_count += 1
            elif token == '}':
                self.br_count -= 1
                if self.br_count == 0:
                    self._state = self._GLOBAL
                    self.univeral_code.END_OF_FUNCTION()
                    return
        if self._is_condition(token):
            self.univeral_code.CONDITION()
        else:
            self.univeral_code.TOKEN()


class ObjCReader(CLikeReader):
    def __init__(self):
        super(ObjCReader, self).__init__()

    def _DEC_TO_IMP(self, token):
        if token in ("+", "-"):
            self._state = self._GLOBAL
        else:
            super(ObjCReader, self)._DEC_TO_IMP(token)
            if self._state == self._GLOBAL:
                self._state = self._OBJC_DEC_BEGIN
                self.univeral_code.START_NEW_FUNCTION(token, self.current_line)

    def _OBJC_DEC_BEGIN(self, token):
        if token == ':':
            self._state = self._OBJC_DEC
            self.univeral_code.ADD_TO_FUNCTION_NAME(token)
        elif token == '{':
            self.br_count += 1
            self._state = self._IMP
        else:
            self._state = self._GLOBAL

    def _OBJC_DEC(self, token):
        if token == '(':
            self._state = self._OBJC_PARAM_TYPE
            self.univeral_code.ADD_TO_LONG_FUNCTION_NAME(token)
        elif token == ',':
            pass
        elif token == '{':
            self.br_count += 1
            self._state = self._IMP
        else:
            self._state = self._OBJC_DEC_BEGIN
            self.univeral_code.ADD_TO_FUNCTION_NAME(" " + token)

    def _OBJC_PARAM_TYPE(self, token):
        if token == ')':
            self._state = self._OBJC_PARAM
        self.univeral_code.ADD_TO_LONG_FUNCTION_NAME(" " + token)

    def _OBJC_PARAM(self, token):
        self._state = self._OBJC_DEC


def compile_file_extension_re(*exts):
    return re.compile(r".*\.(" + r"|".join(exts) + r")$", re.IGNORECASE)

class LanguageChooser(object):

    lizard_language_infos = {
                     'c/c++': {
                          'name_pattern': compile_file_extension_re("c", "cpp", "cc", "mm", "cxx", "h", "hpp"),
                          'reader':CLikeReader},
                     'Java': {
                          'name_pattern': compile_file_extension_re("java"),
                          'reader':CLikeReader},
                      'objC' : {
                          'name_pattern': compile_file_extension_re("m"),
                          'reader':ObjCReader}
                    }

    def get_language_by_filename(self, filename):
        for lan in self.lizard_language_infos:
            info = self.lizard_language_infos[lan]
            if info['name_pattern'].match(filename):
                return lan

    def get_reader_by_file_name_otherwise_default(self, filename):
        lan = self.get_language_by_filename(filename)
        return self.lizard_language_infos[lan or "c/c++"]['reader']()


class FileAnalyzer:
    ''' A FileAnalyzer works as a function. It takes filename as parameter.
        Returns a list of function infos in this file.
    '''

    def __init__(self, noCountPre=False):
        self.no_preprocessor_count = noCountPre

    def __call__(self, filename):
        try:
            with open(filename) as f:
                return self.analyze_source_code(filename, f.read())
        except Exception as e:
            msg = '\n'.join(traceback.format_exception_only(type(e), e))
            msg+= "\nIf you think this is a bug, "+ BUG_REPORTING
            sys.stderr.write(msg)

    def analyze_source_code(self, filename, code):
        try:
            reader = LanguageChooser().get_reader_by_file_name_otherwise_default(filename)
            if self.no_preprocessor_count and hasattr(reader, 'remove_hash_if_from_conditions'):
                reader.remove_hash_if_from_conditions()
            result = self.analyze_source_code_with_parser(filename, code, reader)

            return result
        except ParsingError as e:
            e.filename = filename
            e.code = code
            raise

    def analyze_source_code_with_parser(self, filename, code, parser):
        tokens = generate_tokens(code)
        parsed_code = parser.generate_universal_code(tokens)
        function_list = parsed_code.function_list
        return FileInformation(filename, parsed_code.nloc, function_list)


analyze_file = FileAnalyzer()


class FreeFormattingTokenizer(object):
    '''
    Use this tokenizer to tokenize C/C++, Java, ObjC code, which the
    format is not part of the syntax. So indentation & new lines
    doesn't matter.
    '''

    token_pattern = re.compile(r"(\w+|/\*|//|:=|::|>=|\*=|\*\*|\*|>"+
                           r"|&=|&&|&"+
                           r"|#\s*define|#\s*if|#\s*else|#\s*endif|#\s*\w+"+
                           r"|[!%^&\*\-=+\|\\<>/\]\+]+|.)", re.M | re.S)


    def __call__(self, source_code):
        for t, l in self._generate_tokens_without_empty_lines(source_code):
            if not any(t.startswith(x) for x in ('#define', '/*', '//')) :
                yield t, l

    def _generate_tokens_without_empty_lines(self, source_code):
        in_middle_of_empty_lines = False
        for (token, line) in self._tokens_from_code_with_multiple_newlines(source_code):
            if token != '\n' or not in_middle_of_empty_lines:
                yield token, line
            in_middle_of_empty_lines = (token == '\n')

    def _tokens_from_code_with_multiple_newlines(self, source_code):
        index = 0
        line = 1
        while index >= 0:
            m = self.token_pattern.match(source_code, index)
            if not m:
                break
            index, token = self._read_one_token(source_code, index, m.group(0))            
            line += 1 if token == '\n' else (len(token.splitlines()) - 1)
            if not token.isspace() or token == '\n':
                yield token, line

    def _read_one_token(self, source_code, index, token):
        original_index = index
        if token.startswith("#"):
            token = "#" + token[1:].strip()

        if token == "#define":
            while(1):
                bindex = index + 1
                index = source_code.find('\n', bindex)
                if index == -1:
                    break
                if not source_code[bindex:index].rstrip().endswith('\\'):
                    break
            if index != -1:
                token = source_code[original_index:index]
        elif token == '/*':
            index = source_code.find("*/", index + 2)
            if index != -1:
                index += 2
                token = source_code[original_index:index]
        elif token in( '//', '#if','#endif'):
            index = source_code.find('\n', index)
        elif token == '"' or token == '\'':
            while(1):
                index += 1
                index = source_code.find(token, index)
                if index == -1:
                    break
                if source_code[index - 1] == '\\':
                    if source_code[index - 2] != '\\':
                        continue
                break
            if index != -1:
                token = source_code[original_index:index + 1]
                index = index + 1
        else:
            index += len(token)
        return index, token

generate_tokens = FreeFormattingTokenizer()


import sys

def print_function_info_header():
    print("==============================================================")
    print("  nloc    CCN  token  param    function@line@file")
    print("--------------------------------------------------------------")

def print_function_info(fun, filename, option):
    output_params = {
        'nloc': fun.nloc,
        'CCN': fun.cyclomatic_complexity,
        'token': fun.token_count,
        'param': fun.parameter_count,
        'name': fun.name,
        'line': fun.start_line,
        'file': filename
    }
    output_format = "%(nloc)6d %(CCN)6d %(token)6d %(param)6d    %(name)s@%(line)s@%(file)s"
    if option.verbose:
        output_params['name'] = fun.long_name
    if option.warnings_only:
        output_format = "%(file)s:%(line)s: warning: %(name)s has %(CCN)d CCN and %(param)d params (%(nloc)d NLOC, %(token)d tokens)"
    print(output_format % output_params)

def print_warnings(option, saved_result):
    warning_count = 0
    if not option.warnings_only:
        print(("\n" +
               "======================================\n" +
              "!!!! Warnings (CCN > %d) !!!!") % option.CCN)
        print_function_info_header()
    for file_info in saved_result:
        if file_info:
            for fun in file_info.function_list:
                if fun.cyclomatic_complexity > option.CCN or \
                        fun.parameter_count > option.arguments:
                    warning_count += 1
                    print_function_info(fun, file_info.filename, option)

    if warning_count == 0:
        print("No warning found. Excellent!")

    return warning_count

def print_total(warning_count, saved_result, option):
    file_infos = list(file_info for file_info in saved_result if file_info)
    all_fun = list(itertools.chain(*(file_info.function_list for file_info in file_infos)))
    cnt = len(all_fun)
    if (cnt == 0):
        cnt = 1
    files_NLOC = sum([f.nloc for f in file_infos])
    functions_NLOC = sum([f.nloc for f in all_fun])
    if (functions_NLOC == 0):
        functions_NLOC = 1
    total_info = (
                  files_NLOC,
                  functions_NLOC / cnt,
                  float(sum([f.cyclomatic_complexity for f in all_fun])) / cnt,
                  float(sum([f.token_count for f in all_fun])) / cnt,
                  cnt,
                  warning_count,
                  float(warning_count) / cnt,
                  float(sum([f.nloc for f in all_fun if f.cyclomatic_complexity > option.CCN])) / functions_NLOC
                  )

    if not option.warnings_only:
        print("=================================================================================")
        print("Total nloc  Avg.nloc  Avg CCN  Avg token  Fun Cnt  Warning cnt   Fun Rt   nloc Rt  ")
        print("--------------------------------------------------------------------------------")
        print("%10d%10d%9.2f%11.2f%9d%13d%10.2f%8.2f" % total_info)

def print_and_save_detail_information(allStatistics, option):
    all_functions = []
    if (option.warnings_only):
        all_functions = allStatistics
    else:
        print_function_info_header()
        for fileStatistics in allStatistics:
            if fileStatistics:
                all_functions.append(fileStatistics)
                for fun in fileStatistics.function_list:
                    print_function_info(fun, fileStatistics.filename, option)

        print("--------------------------------------------------------------")
        print("%d file analyzed." % (len(all_functions)))
        print("==============================================================")
        print("NLOC    Avg.NLOC AvgCCN Avg.ttoken  function_cnt    file")
        print("--------------------------------------------------------------")
        for fileStatistics in all_functions:
            print("%7d%7d%7d%10d%10d     %s" % (
                            fileStatistics.nloc, 
                            fileStatistics.average_NLOC, 
                            fileStatistics.average_CCN, 
                            fileStatistics.average_token, 
                            len(fileStatistics.function_list), 
                            fileStatistics.filename))

    return all_functions

def print_result(r, option):
    all_functions = print_and_save_detail_information(r, option)
    warning_count = print_warnings(option, all_functions)
    print_total(warning_count, all_functions, option)
    if option.number > warning_count:
        sys.exit(1)

class XMLFormatter(object):

    def xml_output(self, result, options):
        ''' Thanks for Holy Wen from Nokia Siemens Networks to let me use his code
            to put the result into xml file that is compatible with cppncss.
            Jenkens has plugin for cppncss format result to display the diagram.
        '''
        import xml.dom.minidom

        impl = xml.dom.minidom.getDOMImplementation()
        doc = impl.createDocument(None, "cppncss", None)
        root = doc.documentElement

        pi = doc.createProcessingInstruction('xml-stylesheet','type="text/xsl" href="https://raw.github.com/terryyin/lizard/master/lizard.xsl"')
        doc.insertBefore(pi, root)

        measure = doc.createElement("measure")
        measure.setAttribute("type", "Function")
        measure.appendChild(self._createLabels(doc, ["Nr.", "NCSS", "CCN"]))

        Nr = 0
        total_func_ncss = 0
        total_func_ccn = 0

        for source_file in result:
            file_name = source_file.filename
            for func in source_file.function_list:
                Nr += 1
                total_func_ncss += func.nloc
                total_func_ccn += func.cyclomatic_complexity
                measure.appendChild(self._createFunctionItem(doc, Nr, file_name, func, options.verbose))

            if Nr != 0:
                measure.appendChild(self._createLabeledValueItem(doc, 'average', "NCSS", str(total_func_ncss / Nr)))
                measure.appendChild(self._createLabeledValueItem(doc, 'average', "CCN", str(total_func_ccn / Nr)))

        root.appendChild(measure)

        measure = doc.createElement("measure")
        measure.setAttribute("type", "File")
        measure.appendChild(self._createLabels(doc, ["Nr.", "NCSS", "CCN", "Functions"]))

        file_NR = 0
        file_total_ncss = 0
        file_total_ccn = 0
        file_total_funcs = 0

        for source_file in result:
            file_NR += 1
            file_total_ncss += source_file.nloc
            file_total_ccn += source_file.CCN
            file_total_funcs += len(source_file.function_list)
            measure.appendChild(self._createFileNode(doc, source_file, file_NR))

        if file_NR != 0:
            fileSummary = [("NCSS", file_total_ncss / file_NR),
                           ("CCN", file_total_ccn / file_NR),
                           ("Functions", file_total_funcs / file_NR)]
            for k, v in fileSummary:
                measure.appendChild(self._createLabeledValueItem(doc, 'average', k, v))

        summary = [("NCSS", file_total_ncss),
                       ("CCN", file_total_ccn ),
                       ("Functions", file_total_funcs)]
        for k, v in summary:
            measure.appendChild(self._createLabeledValueItem(doc, 'sum', k, v))

        root.appendChild(measure)

        xmlString = doc.toprettyxml()
        return xmlString

    def _createLabel(self, doc, name):
        label = doc.createElement("label")
        text1 = doc.createTextNode(name)
        label.appendChild(text1)
        return label

    def _createLabels(self, doc, labelNames):
        labels = doc.createElement("labels")
        for label in labelNames:
            labels.appendChild(self._createLabel(doc, label))

        return labels

    def _createFunctionItem(self, doc, Nr, file_name, func, verbose):
        item = doc.createElement("item")
        if verbose:
            item.setAttribute("name", "%s at %s:%s" % (func.long_name, file_name, func.start_line))
        else:
            item.setAttribute("name", "%s(...) at %s:%s" % (func.name, file_name, func.start_line))
        value1 = doc.createElement("value")
        text1 = doc.createTextNode(str(Nr))
        value1.appendChild(text1)
        item.appendChild(value1)
        value2 = doc.createElement("value")
        text2 = doc.createTextNode(str(func.nloc))
        value2.appendChild(text2)
        item.appendChild(value2)
        value3 = doc.createElement("value")
        text3 = doc.createTextNode(str(func.cyclomatic_complexity))
        value3.appendChild(text3)
        item.appendChild(value3)
        return item


    def _createLabeledValueItem(self, doc, name, label, value):
        average_ncss = doc.createElement(name)
        average_ncss.setAttribute("lable", label)
        average_ncss.setAttribute("value", str(value))
        return average_ncss


    def _createFileNode(self, doc, source_file, file_NR):
        item = doc.createElement("item")
        item.setAttribute("name", source_file.filename)
        value1 = doc.createElement("value")
        text1 = doc.createTextNode(str(file_NR))
        value1.appendChild(text1)
        item.appendChild(value1)
        value2 = doc.createElement("value")
        text2 = doc.createTextNode(str(source_file.nloc))
        value2.appendChild(text2)
        item.appendChild(value2)
        value3 = doc.createElement("value")
        text3 = doc.createTextNode(str(source_file.CCN))
        value3.appendChild(text3)
        item.appendChild(value3)
        value4 = doc.createElement("value")
        text4 = doc.createTextNode(str(len(source_file.function_list)))
        value4.appendChild(text4)
        item.appendChild(value4)
        return item

def createlizardCommandLineParser():
    from optparse import OptionParser
    parser = OptionParser(version=VERSION)
    parser.add_option("-v", "--verbose",
            help="Output in verbose mode (long function name)",
            action="store_true",
            dest="verbose",
            default=False)
    parser.add_option("-C", "--CCN",
            help =  "Threshold for cyclomatic complexity number warning. "+
                    "The default value is %d. Functions with CCN bigger than this number will generate warning" % DEFAULT_CCN_THRESHOLD,
            action="store",
            type="int",
            dest="CCN",
            default=DEFAULT_CCN_THRESHOLD)
    parser.add_option("-a", "--arguments",
            help="Limit for number of parameters",
            action="store",
            type="int",
            dest="arguments",
            default=100)
    parser.add_option("-w", "--warnings_only",
            help="Show warnings only, using clang/gcc's warning format for printing warnings. http://clang.llvm.org/docs/UsersManual.html#cmdoption-fdiagnostics-format",
            action="store_true",
            dest="warnings_only",
            default=False)
    parser.add_option("-i", "--ignore_warnings",
            help="If the number of warnings is equal or less than the number, the tool will exit normally, otherwize it will generate error. Useful in makefile when improving legacy code.",
            action="store",
            type="int",
            dest="number",
            default=0)
    parser.add_option("-x", "--exclude",
            help="Exclude files that match this pattern. * matches everything, ? matches any single characoter, \"./folder/*\" exclude everything in the folder, recursively. Multiple patterns can be specified. Don't forget to add \"\" around the pattern.",
            action="append",
            dest="exclude",
            default=[])
    parser.add_option("-X", "--xml",
            help="Generate XML in cppncss style instead of the normal tabular output. Useful to generate report in Jenkins server",
            action="store_true",
            dest="xml",
            default=None)
    parser.add_option("-P", "--no_preprocessor_count",
            help="By default, a #if will also increase the complexity. Adding this option to ignore them",
            action="store_true",
            dest="no_preprocessor_count",
            default=False)
    parser.add_option("-t", "--working_threads",
            help="number of working threads. The default value is 1.",
            action="store",
            type="int",
            dest="working_threads",
            default=1)
    parser.add_option("-d", "--find_duplicates",
            help="find and skip analysis for duplicates",
            action="store_true",
            dest="duplicates",
            default=False)

    parser.usage = "lizard [options] [PATH or FILE] [PATH] ... "
    parser.description = __doc__
    return parser

def mapFilesToAnalyzer(files, fileAnalyzer, working_threads):
    try:
        # python 2.6 cannot work properly with multiple threading
        if sys.version_info[0:2] == (2, 6):
            raise
        import multiprocessing
        it = multiprocessing.Pool(processes=working_threads)
        mapFun = it.imap_unordered
    except:
        try:
            mapFun = itertools.imap
        except:
            mapFun = map
    r = mapFun(fileAnalyzer, files)
    return r

import os
import fnmatch

import hashlib

def _md5HashFile(full_path_name):
    ''' return md5 hash of a file '''
    with open(full_path_name, mode='r') as source_file:
        if sys.version_info[0] == 3:
            code_md5 = hashlib.md5(source_file.read().encode('utf-8'))
        else:
            code_md5 = hashlib.md5(source_file.read())
    return code_md5.hexdigest()

def _notDuplicate(full_path_name, hash_set):
    ''' Function counts md5 hash for the given file and checks if it isn't a duplicate using set of hashes for previous files '''
    fhash = _md5HashFile(full_path_name)
    if fhash and fhash not in hash_set:
        hash_set.add(fhash)
        return True
    else:
        return False

def _notExluded(str_to_match, patterns):
    return LanguageChooser().get_language_by_filename(str_to_match) and \
        all(not fnmatch.fnmatch(str_to_match, p) for p in patterns)

def checkFile(full_path_name, exclude_patterns, hash_set, check_duplicates):
    ''' simplify the getSourceFiles function  '''
    if _notExluded(full_path_name, exclude_patterns):
        if check_duplicates:
            return _notDuplicate(full_path_name, hash_set)
        else:
            return True
    else:
        return False

def getSourceFiles(SRC_DIRs, exclude_patterns, check_duplicates=False):
    hash_set = set()
    for SRC_DIR in SRC_DIRs:
        if os.path.isfile(SRC_DIR) and LanguageChooser().get_language_by_filename(SRC_DIR):
            yield SRC_DIR
        else:
            for root, _, files in os.walk(SRC_DIR, topdown=False):
                for filename in files:
                    full_path_name = os.path.join(root, filename)
                    if checkFile(full_path_name, exclude_patterns, hash_set, check_duplicates):
                        yield full_path_name

def analyze(paths, options):
    ''' This is the most important function of lizard.
        It analyze the given paths with the options.
        Can be used directly by other Python application.
    '''
    files = getSourceFiles(paths, options.exclude, options.duplicates)
    fileAnalyzer = FileAnalyzer(options.no_preprocessor_count)
    r = mapFilesToAnalyzer(files, fileAnalyzer, options.working_threads)
    return r

def lizard_main(argv):
    options, args = createlizardCommandLineParser().parse_args(args=argv)
    paths = ["."] if len(args) == 1 else args[1:]
    r = analyze(paths, options)
    if options.xml:
        print (XMLFormatter().xml_output(list(r), options))
    else:
        print_result(r, options)

def main():
    lizard_main(sys.argv)

if __name__ == "__main__":
    main()
