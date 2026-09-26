<?php
// This file is part of Moodle - http://moodle.org/
//
// Moodle is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// Moodle is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with Moodle.  If not, see <https://www.gnu.org/licenses/>.

/**
 * AJAX endpoint for saving packages from the embedded eXeLearning editor.
 *
 * Receives an exported package, stores it in filearea "package", then updates
 * module metadata. Old package files are deleted only after the new one is
 * successfully stored and processed.
 *
 * @package    mod_exelearning
 * @copyright  2025 eXeLearning
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

define('AJAX_SCRIPT', true);

require('../../../config.php');
require_once($CFG->dirroot . '/mod/exelearning/lib.php');

$cmid = required_param('cmid', PARAM_INT);
$format = 'elpx';

$cm = get_coursemodule_from_id('exelearning', $cmid, 0, false, MUST_EXIST);
$course = $DB->get_record('course', ['id' => $cm->course], '*', MUST_EXIST);
$exelearning = $DB->get_record('exelearning', ['id' => $cm->instance], '*', MUST_EXIST);

require_login($course, true, $cm);
require_sesskey();
$context = context_module::instance($cm->id);
require_capability('moodle/course:manageactivities', $context);
// Embedded editing can be switched off site-wide (DEC-108-01): refuse saves too,
// not only the editor bootstrap — this is the state-changing half of the flow.
exelearning_require_embedded_editor_enabled();

header('Content-Type: application/json; charset=utf-8');

$lock = null;

try {
    if (empty($_FILES['package'])) {
        throw new moodle_exception('nofile', 'error');
    }

    $uploadedfile = $_FILES['package'];
    if ((int)$uploadedfile['error'] !== UPLOAD_ERR_OK) {
        throw new moodle_exception('uploadproblem', 'error');
    }
    $lock = \mod_exelearning\local\package_manager::get_package_lock((int) $exelearning->id);
    if (!$lock) {
        throw new moodle_exception('locktimeout');
    }
    // The viewer may have refreshed the runtime since this request loaded the row.
    $exelearning = $DB->get_record('exelearning', ['id' => $cm->instance], '*', MUST_EXIST);
    $filename = clean_filename($uploadedfile['name']);
    if (empty($filename)) {
        $filename = 'package.elpx';
    }

    // Stage the package as the next revision, extract and validate it, then advance the
    // pointer and prune the superseded revision — all only on success (issue 73). A
    // corrupt save throws BEFORE the pointer moves and drops the staged package, so the
    // previous package + content (and revision) stay intact. Editing in the embedded
    // editor can add or remove gradable iDevices, so the gradebook columns are re-synced
    // afterwards: new iDevices create columns, removed ones are marked deleted (grade
    // history preserved).
    \mod_exelearning\local\package_manager::save_editor_package(
        $context,
        $exelearning,
        $uploadedfile['tmp_name'],
        $filename,
        $USER
    );
    $delta = exelearning_sync_grade_items($exelearning->id, $context->id);
    // If editing changed the gradable set (added/removed/edited-options) and
    // attempts exist, warn that prior grades are not recomputed (DEC-12-01). The
    // editor reloads view.php after a successful save (amd/src/editor_modal.js),
    // so this queued notification surfaces there without any JS change.
    exelearning_warn_if_grades_stale($exelearning->id, $delta, $cmid);

    echo json_encode([
        'success' => true,
        'revision' => $exelearning->revision,
        'format' => $format,
    ]);
} catch (Throwable $e) {
    debugging('mod_exelearning editor save failed: ' . $e->getMessage(), DEBUG_DEVELOPER);
    http_response_code(500);
    // A moodle_exception message is a translated string meant for users (e.g. the
    // maxbytesfile limit from package_manager), so the editor can show it; any other
    // Throwable may leak internals (paths, SQL), so it stays generic.
    echo json_encode([
        'success' => false,
        'error' => $e instanceof moodle_exception ? $e->getMessage() : get_string('error'),
    ]);
} finally {
    if ($lock) {
        $lock->release();
    }
}
