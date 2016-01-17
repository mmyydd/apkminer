#!/usr/bin/env python

import sys
import time
import pprint
import signal
import logging
import argparse
import traceback
import cStringIO
import multiprocessing as mp

import os
from os import listdir
from os.path import isfile, join

from androguard.core.bytecodes import apk
from androguard.core.bytecodes import dvm
from androguard.core.analysis import analysis

from analyzers import *

def get_files_in_dir(dir_path):
	return [f for f in listdir(dir_path) if isfile(join(dir_path, f))]

def logger_runner(log_file, res_queue):
	print "started logger"
	fd = open(log_file, "a")
	while True:
		res_queue.get(True)
		log_data = res_queue.get()
		fd.write(log_data)
		fd.flush()

def runner(func, args, queue, res_queue):
	try:
		func(args, queue, res_queue)
	except:
		raise Exception("".join(traceback.format_exception(*sys.exc_info())))

def init_worker():
	signal.signal(signal.SIGINT, signal.SIG_IGN)

def main():
	parser = argparse.ArgumentParser(description='analyzer of APKs')
	parser.add_argument("-i", "--in_dir", type=str,
						help="directory of apk files to analyze", default=None)
	parser.add_argument("-o", "--log_file", type=str,
						help="log file to write to", default="OUTPUT.log")
	parser.add_argument("-c", "--cores", type=int,
						help="force a number of cores to use")
	parser.add_argument("-a", "--analyzer", type=str,
						help="Select the analyzer you want to use.", default="elf_files")
	parser.add_argument("-l", "--list_analyzers", action="store_true",
						help="List the possible analyzers")

	args = parser.parse_args()

	# Complete listing of possible analyzers
	analyzer_funcs = {'elf_files': elf_files,
					  'private_key': private_keys,
					  'amazon_finder': aws_finder,
					  'silverpush': silverpush}

	if args.list_analyzers:
		print "Analyzers:"
		for func_name, func in analyzer_funcs.iteritems():
			print "  %s" % func_name
		return

	if not args.in_dir:
		print "Please provide a input directory with -i"
		return

	selected_analyzer = None
	for func_name, func in analyzer_funcs.iteritems():
		if func_name == args.analyzer:
			selected_analyzer = func
			break
	if not selected_analyzer:
		print "You selected a bad analyzer [%s]" % args.analyzer
		print "Analyzers:"
		for func_name, func in analyzer_funcs.iteritems():
			print "  %s" % func_name

		return

	if args.cores:
		cores = args.cores
	else:
		cores = mp.cpu_count()

	print "Started '%s' analyzer with %d cores, log file: %s" % (selected_analyzer.__name__, cores, args.log_file)
	apk_files = get_files_in_dir(args.in_dir)

	# Enable for debugging info.
	# mp.log_to_stderr(logging.DEBUG)
	manager = mp.Manager()
	pool = mp.Pool(cores + 2, init_worker)

	apk_queue = manager.Queue()
	res_queue = manager.Queue()
	lock = manager.Lock()

	# if we have a small count of APK files, limit our worker count
	apk_count = len(apk_files)
	if apk_count < cores:
		cores = apk_count

	for apk in apk_files:
		apk_queue.put(apk)

	try:
		# TODO: make the runner handle multiple arg lists?
		log_result = pool.apply_async(logger_runner, (args.log_file, res_queue))
		
		worker_results = []
		for i in xrange(0, cores):
			worker_results.append(pool.apply_async(runner, (selected_analyzer.analyze, args, apk_queue, res_queue)))
		pool.close()

		for res in worker_results:
			result = res.get()
			if not res.successful():
				print "one of the workers failed"

		print "completed all work"
		pool.terminate()
		pool.join()

	except KeyboardInterrupt:
		print "Exiting!"
		pool.terminate()
		pool.join()
	
if __name__ == '__main__':
	main()
